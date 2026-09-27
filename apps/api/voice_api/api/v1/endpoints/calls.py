"""Queue telephone requests and launch the fenced, evidence-producing runtime."""

import asyncio
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import httpx
from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from voice_api.api.deps import get_session, require_operator
from voice_api.core.config import get_settings
from voice_api.models import Call, Run
from voice_api.schemas.call import StartCallBody
from voice_api.services.call_service import queue_call
from voice_runtime.execution.native import NativePipelineHost
from voice_runtime.execution.runner import execute_call
from voice_runtime.telephony.driver import Sim7600CallDriver

router = APIRouter(tags=["calls"])
Session = Depends(get_session)
Operator = Depends(require_operator)
_background_call_tasks: set[asyncio.Task] = set()


async def _run_live_call_background(run_id: str, endpoint_id: str) -> None:
    from voice_api.main import app

    settings = get_settings()
    host = NativePipelineHost(run_id, Path(settings.recordings_dir), settings)
    driver = Sim7600CallDriver(host)
    headers = {"Authorization": f"Bearer {settings.operator_token}"}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://runtime.local"
    ) as client:

        async def register_artifacts() -> None:
            if not host.directory.exists():
                return
            for kind in ("input", "output", "mixed", "pipeline_log"):
                filename = "pipeline.log" if kind == "pipeline_log" else f"{kind}.wav"
                if not (host.directory / filename).is_file():
                    continue
                response = await client.post(
                    f"/api/runs/{run_id}/artifacts",
                    headers=headers,
                    json={
                        "id": str(uuid5(NAMESPACE_URL, f"{run_id}/{kind}")),
                        "kind": kind,
                        "path": f"{run_id}/{filename}",
                    },
                )
                response.raise_for_status()

        try:
            await execute_call(
                client,
                settings.operator_token,
                run_id,
                endpoint_id,
                driver,
                Path("data/evidence") / f"{run_id}.jsonl",
                secrets=tuple(
                    secret
                    for secret in (
                        settings.groq_api_key,
                        settings.jev_api_key,
                        settings.sarvam_api_key,
                        settings.cartesia_api_key,
                        settings.gemini_api_key,
                    )
                    if secret
                ),
                after_close=register_artifacts,
            )
        except Exception:
            logger.error("Live call {} stopped; inspect claim and evidence status", run_id)


def _spawn_call_task(run_id: str, endpoint_id: str) -> None:
    task = asyncio.create_task(_run_live_call_background(run_id, endpoint_id))
    _background_call_tasks.add(task)
    task.add_done_callback(_background_call_tasks.discard)


@router.post("/calls", status_code=201)
async def start_call(
    body: StartCallBody, session: AsyncSession = Session, _: None = Operator
) -> dict:
    is_twilio = body.telephony is not None and body.telephony.provider == "twilio"
    if body.dispatch:
        if is_twilio:
            if not get_settings().public_base_url:
                raise HTTPException(422, "Twilio dispatch requires VOICE_PUBLIC_BASE_URL")
        else:
            endpoint = body.telephony.endpoint_id if body.telephony else body.endpoint_id
            if not endpoint or not get_settings().operator_token:
                raise HTTPException(422, "Dispatch needs an endpoint and operator token")

    run, call = await queue_call(
        session,
        body.contact_id,
        body.agent_version_id,
        body.endpoint_id,
        body.logging_override,
        body.telephony,
    )
    await session.commit()

    if body.dispatch:
        if is_twilio:
            from voice_api.models.common import now
            from voice_api.services.twilio_service import resolve_twilio_credentials
            from voice_runtime.telephony.twilio import PublicTelephonyUrls, TwilioCallController

            settings = get_settings()
            public_urls = PublicTelephonyUrls(settings.public_base_url)
            _, creds = await resolve_twilio_credentials(session, call.telephony_connection_id)
            controller = TwilioCallController(creds)
            try:
                call_sid = await controller.dial(
                    to=call.target_snapshot,
                    from_number=call.from_number,
                    media_ws_url=public_urls.twilio_media(call.correlation_id),
                    status_callback_url=public_urls.twilio_call_status(call.correlation_id),
                    stream_status_callback_url=public_urls.twilio_stream_status(
                        call.correlation_id
                    ),
                    correlation_id=call.correlation_id,
                    run_id=run.id,
                )
                call.provider_call_id = call_sid
                call.status = "dialing"
                await session.commit()
            except Exception as err:
                logger.exception("Failed to place Twilio outbound call: {}", err)
                call.status = "failed"
                run.status = "failed"
                call.ended_at = now()
                run.ended_at = now()
                error_msg = getattr(err, "msg", None) or str(err)
                if creds and creds.auth_token and creds.auth_token in error_msg:
                    error_msg = error_msg.replace(creds.auth_token, "[REDACTED]")
                meta = dict(call.provider_metadata or {})
                meta["error"] = error_msg
                call.provider_metadata = meta
                await session.commit()
                raise HTTPException(502, f"Failed to place Twilio call: {error_msg}") from err
        else:
            endpoint = body.telephony.endpoint_id if body.telephony else body.endpoint_id
            _spawn_call_task(run.id, endpoint)

    return {
        "run_id": run.id,
        "call_id": call.id,
        "provider": getattr(call, "provider", "sim7600"),
        "status": call.status if is_twilio else ("dispatching" if body.dispatch else "queued"),
        "target": call.target_snapshot,
    }


@router.get("/calls")
async def list_calls(session: AsyncSession = Session, _: None = Operator) -> dict:
    rows = (await session.scalars(select(Call).order_by(Call.created_at.desc()))).all()
    return {"calls": [_call_response(call) for call in rows]}


def _call_response(call: Call) -> dict:
    return {
        "id": call.id,
        "run_id": call.run_id,
        "contact_id": call.contact_id,
        "agent_version_id": call.agent_version_id,
        "target_snapshot": call.target_snapshot,
        "provider": call.provider,
        "from_number": call.from_number,
        "telephony_connection_id": call.telephony_connection_id,
        "status": call.status,
        "recording_path": call.recording_path,
        "answered_at": call.answered_at,
        "ended_at": call.ended_at,
        "created_at": call.created_at,
    }


@router.get("/calls/{call_id}")
async def get_call(call_id: str, session: AsyncSession = Session, _: None = Operator) -> dict:
    call = await session.get(Call, call_id)
    if call is None:
        raise HTTPException(404, "Call not found")
    return _call_response(call)


@router.post("/calls/{call_id}/dispatch")
async def dispatch_queued_call(
    call_id: str, session: AsyncSession = Session, _: None = Operator
) -> dict:
    call = await session.get(Call, call_id)
    if call is None:
        raise HTTPException(404, "Call not found")
    if call.status != "queued":
        raise HTTPException(409, "Only queued calls can be dispatched")
    run = await session.get(Run, call.run_id) if call.run_id else None
    if run is None:
        raise HTTPException(404, "Run not found")

    if call.provider == "twilio":
        from voice_api.models.common import now
        from voice_api.services.twilio_service import resolve_twilio_credentials
        from voice_runtime.telephony.twilio import PublicTelephonyUrls, TwilioCallController

        settings = get_settings()
        if not settings.public_base_url:
            raise HTTPException(422, "Twilio dispatch requires VOICE_PUBLIC_BASE_URL")
        public_urls = PublicTelephonyUrls(settings.public_base_url)
        _, creds = await resolve_twilio_credentials(session, call.telephony_connection_id)
        controller = TwilioCallController(creds)
        try:
            call_sid = await controller.dial(
                to=call.target_snapshot,
                from_number=call.from_number,
                media_ws_url=public_urls.twilio_media(call.correlation_id),
                status_callback_url=public_urls.twilio_call_status(call.correlation_id),
                stream_status_callback_url=public_urls.twilio_stream_status(call.correlation_id),
                correlation_id=call.correlation_id,
                run_id=run.id,
            )
            call.provider_call_id = call_sid
            call.status = "dialing"
            await session.commit()
        except Exception as err:
            logger.exception("Failed to place Twilio outbound call: {}", err)
            call.status = "failed"
            run.status = "failed"
            call.ended_at = now()
            run.ended_at = now()
            meta = dict(call.provider_metadata or {})
            meta["error"] = str(err)
            call.provider_metadata = meta
            await session.commit()
            raise HTTPException(502, f"Failed to place Twilio call: {err}") from err
        return {
            "run_id": run.id,
            "call_id": call.id,
            "provider": call.provider,
            "status": "dialing",
            "target": call.target_snapshot,
        }

    if not run.endpoint_id or not get_settings().operator_token:
        raise HTTPException(422, "Dispatch needs an endpoint and operator token")
    _spawn_call_task(run.id, run.endpoint_id)
    return {
        "run_id": run.id,
        "call_id": call.id,
        "provider": call.provider,
        "status": "dispatching",
        "target": call.target_snapshot,
    }
