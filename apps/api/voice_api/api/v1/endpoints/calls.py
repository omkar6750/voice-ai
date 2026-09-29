"""Queue telephone requests and launch the fenced, evidence-producing runtime."""

import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from voice_api.api.deps import get_session, require_legacy_owner
from voice_api.core.config import get_settings
from voice_api.core.security import allow_organization_member
from voice_api.models import Call, Run
from voice_api.schemas.call import StartCallBody
from voice_api.services.call_service import queue_call
from voice_api.services.local_runtime_service import (
    LocalEvidenceIngestor,
    local_claim,
    local_progress,
    register_local_artifacts,
)
from voice_api.services.provider_credentials import settings_for_run
from voice_runtime.execution.native import NativePipelineHost
from voice_runtime.execution.runner import execute_call
from voice_runtime.telephony.driver import Sim7600CallDriver

router = APIRouter(tags=["calls"])
Session = Depends(get_session)
Operator = Depends(require_legacy_owner)
_background_call_tasks: set[asyncio.Task] = set()


async def _run_live_call_background(run_id: str, endpoint_id: str) -> None:
    settings = await settings_for_run(run_id, get_settings())
    host = NativePipelineHost(run_id, Path(settings.recordings_dir), settings)
    driver = Sim7600CallDriver(host)

    async def post(suffix: str, body: dict) -> dict:
        if suffix == "claim":
            return await local_claim(run_id, body)
        if suffix == "progress":
            return await local_progress(run_id, body)
        raise ValueError("Unsupported local control operation")

    async def register_artifacts() -> None:
        await register_local_artifacts(run_id, host.directory, strict=True)

    try:
        await execute_call(
            None,
            "",
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
            local_post=post,
            local_ingestor=LocalEvidenceIngestor(run_id),
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
            if not endpoint:
                raise HTTPException(422, "Dispatch needs an endpoint")

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
@allow_organization_member
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
@allow_organization_member
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

    if not run.endpoint_id:
        raise HTTPException(422, "Dispatch needs an endpoint")
    _spawn_call_task(run.id, run.endpoint_id)
    return {
        "run_id": run.id,
        "call_id": call.id,
        "provider": call.provider,
        "status": "dispatching",
        "target": call.target_snapshot,
    }
