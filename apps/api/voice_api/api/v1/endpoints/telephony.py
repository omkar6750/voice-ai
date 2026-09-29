"""Twilio telephony callbacks and WebSocket Media Stream endpoint."""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response, WebSocket
from loguru import logger
from pipecat.runner.utils import parse_telephony_websocket
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)
from sqlalchemy.ext.asyncio import AsyncSession
from twilio.request_validator import RequestValidator
from voice_api.api.deps import get_session
from voice_api.core.config import get_settings
from voice_api.db.session import SessionFactory
from voice_api.db.tenant_scope import bind_call_organization, bind_organization
from voice_api.models import Call, Run
from voice_api.models.common import now
from voice_api.schemas.diagnostics import DiagnosticInput
from voice_api.services.call_service import (
    apply_twilio_call_status,
    apply_twilio_stream_status,
    atomically_claim_run,
    attach_twilio_media,
    get_by_correlation_id,
)
from voice_api.services.diagnostic_service import persist_diagnostic
from voice_api.services.local_runtime_service import LocalEvidenceIngestor, register_local_artifacts
from voice_api.services.provider_credentials import settings_for_organization
from voice_api.services.twilio_service import resolve_twilio_credentials
from voice_runtime.diagnostics import text_error_diagnostic
from voice_runtime.execution.delivery import stream_evidence
from voice_runtime.execution.exchange import ExchangeTracker
from voice_runtime.execution.native import NativePipelineHost
from voice_runtime.execution.spool import DurableSpool
from voice_runtime.telephony.twilio import PublicTelephonyUrls, TwilioCallLifecycle

router = APIRouter(prefix="/telephony", tags=["telephony"])
Session = Depends(get_session)


@router.post("/twilio/call-status/{correlation_id}")
async def twilio_call_status(
    correlation_id: str,
    request: Request,
    session: AsyncSession = Session,
) -> Response:
    await bind_call_organization(session, correlation_id)
    call = await get_by_correlation_id(session, correlation_id)
    if call is None or call.provider != "twilio" or not call.org_id:
        raise HTTPException(404, "Call not found")

    _, credentials = await resolve_twilio_credentials(
        session, call.telephony_connection_id, require_enabled=False
    )
    form = dict(await request.form())
    signature = request.headers.get("x-twilio-signature", "")

    settings = get_settings()
    if not settings.public_base_url:
        raise HTTPException(503, "Twilio callbacks are not configured")
    public_urls = PublicTelephonyUrls(settings.public_base_url)
    validator = RequestValidator(credentials.auth_token)
    if not signature or not validator.validate(
        public_urls.twilio_call_status(correlation_id),
        form,
        signature,
    ):
        raise HTTPException(403, "Invalid Twilio signature")

    if (
        call.provider_call_id
        and form.get("CallSid")
        and form.get("CallSid") != call.provider_call_id
    ):
        raise HTTPException(409, "CallSid mismatch")

    await apply_twilio_call_status(
        session,
        call=call,
        twilio_status=form.get("CallStatus"),
    )
    return Response(status_code=204)


@router.post("/twilio/stream-status/{correlation_id}")
async def twilio_stream_status(
    correlation_id: str,
    request: Request,
    session: AsyncSession = Session,
) -> Response:
    await bind_call_organization(session, correlation_id)
    call = await get_by_correlation_id(session, correlation_id)
    if call is None or call.provider != "twilio" or not call.org_id:
        raise HTTPException(404, "Call not found")

    _, credentials = await resolve_twilio_credentials(
        session, call.telephony_connection_id, require_enabled=False
    )
    form = dict(await request.form())
    signature = request.headers.get("x-twilio-signature", "")

    settings = get_settings()
    if not settings.public_base_url:
        raise HTTPException(503, "Twilio callbacks are not configured")
    public_urls = PublicTelephonyUrls(settings.public_base_url)
    validator = RequestValidator(credentials.auth_token)
    if not signature or not validator.validate(
        public_urls.twilio_stream_status(correlation_id),
        form,
        signature,
    ):
        raise HTTPException(403, "Invalid Twilio signature")

    await apply_twilio_stream_status(
        session,
        call=call,
        stream_sid=form.get("StreamSid"),
        event=form.get("StatusCallbackEvent"),
        error=form.get("StreamError"),
    )
    return Response(status_code=204)


@router.websocket("/twilio/media/{correlation_id}")
async def twilio_media_endpoint(
    websocket: WebSocket,
    correlation_id: str,
) -> None:
    async with SessionFactory() as session:
        try:
            org_id = await bind_call_organization(session, correlation_id)
        except HTTPException:
            await websocket.close(code=1008)
            return
        call = await get_by_correlation_id(session, correlation_id)
        if call is None or call.provider != "twilio" or not call.org_id:
            await websocket.close(code=1008)
            return
        if call.org_id != org_id:
            await websocket.close(code=1008)
            return

        connection_id = call.telephony_connection_id
        run_id = call.run_id
        provider_call_id = call.provider_call_id
        existing_stream_sid = (call.provider_metadata or {}).get("stream_sid")
        call_id = call.id

        if not connection_id or not run_id:
            await websocket.close(code=1008)
            return

        _, credentials = await resolve_twilio_credentials(
            session, connection_id, require_enabled=True
        )
        provider_settings = await settings_for_organization(session, org_id, get_settings())

    settings = provider_settings
    signature = websocket.headers.get("x-twilio-signature", "")
    if not settings.public_base_url:
        await websocket.close(code=1008)
        return
    public_urls = PublicTelephonyUrls(settings.public_base_url)
    validator = RequestValidator(credentials.auth_token)
    if not signature or not validator.validate(
        public_urls.twilio_media(correlation_id),
        {},
        signature,
    ):
        await websocket.close(code=1008)
        return

    await websocket.accept()

    try:
        transport_type, call_data = await parse_telephony_websocket(websocket)
    except Exception:
        await websocket.close(code=1008)
        return

    if transport_type != "twilio":
        await websocket.close(code=1008)
        return

    stream_sid = call_data.get("stream_id")
    call_sid = call_data.get("call_id")
    custom_params = call_data.get("body", {})

    if not stream_sid or not call_sid:
        await websocket.close(code=1008)
        return

    if provider_call_id and provider_call_id != call_sid:
        await websocket.close(code=1008)
        return

    if custom_params.get("run_id") and custom_params["run_id"] != run_id:
        await websocket.close(code=1008)
        return

    if custom_params.get("correlation_id") and custom_params["correlation_id"] != correlation_id:
        await websocket.close(code=1008)
        return

    if existing_stream_sid and existing_stream_sid != stream_sid:
        await websocket.close(code=1008)
        return

    async with SessionFactory() as session:
        bind_organization(session.sync_session, org_id)
        claimed = await atomically_claim_run(session, run_id)
        if not claimed:
            await websocket.close(code=1008)
            return

        c = await session.get(Call, call_id)
        if c:
            await attach_twilio_media(session, c, provider_call_id=call_sid, stream_sid=stream_sid)

        run = await session.get(Run, run_id)
        if not run:
            await websocket.close(code=1008)
            return
        snapshot = run.resolved_config

    pipeline_rate = snapshot.get("audio", {}).get("sample_rate", 16000)
    recordings_dir = Path(settings.recordings_dir)

    serializer = TwilioFrameSerializer(
        stream_sid=stream_sid,
        call_sid=call_sid,
        account_sid=credentials.account_sid,
        auth_token=credentials.auth_token,
        params=TwilioFrameSerializer.InputParams(
            twilio_sample_rate=8000,
            sample_rate=pipeline_rate,
            auto_hang_up=True,
        ),
    )

    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            serializer=serializer,
        ),
    )

    lifecycle = TwilioCallLifecycle()

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(_transport, _ws):
        lifecycle.mark_ended()

    host = NativePipelineHost(
        run_id=run_id,
        recordings_dir=recordings_dir,
        settings=settings,
    )

    spool_path = Path("data/evidence") / f"{run_id}.jsonl"
    spool_path.parent.mkdir(parents=True, exist_ok=True)
    spool = DurableSpool(spool_path)
    secrets = tuple(
        s
        for s in (
            settings.groq_api_key,
            settings.jev_api_key,
            settings.sarvam_api_key,
            settings.cartesia_api_key,
            settings.gemini_api_key,
            credentials.auth_token,
        )
        if s
    )
    tracker = ExchangeTracker(run_id, spool, secrets=secrets)
    ingestor = LocalEvidenceIngestor(run_id, org_id=org_id)
    delivery_task = asyncio.create_task(stream_evidence(spool, ingestor))

    try:
        await host.prepare(snapshot, tracker, transport=transport)
        await host.converse(lifecycle)
    except Exception as exc:
        logger.exception("Twilio pipeline failed during run {}: {}", run_id, exc)
        async with SessionFactory() as session:
            bind_organization(session.sync_session, org_id)
            r = await session.get(Run, run_id)
            if r:
                await persist_diagnostic(
                    session,
                    run_id,
                    DiagnosticInput.model_validate(text_error_diagnostic(str(exc))),
                )
            if r and r.status not in ("completed", "canceled"):
                r.status = "failed"
                r.error = f"Pipeline execution failed: {exc}"
                r.ended_at = now()
            c = await session.get(Call, call_id)
            if c and c.status not in ("completed", "canceled"):
                c.status = "failed"
                c.ended_at = now()
            await session.commit()
    finally:
        lifecycle.mark_ended()
        await host.close()
        delivery_task.cancel()

        async with SessionFactory() as session:
            bind_organization(session.sync_session, org_id)
            r = await session.get(Run, run_id)
            if r and r.status in ("claimed", "running"):
                r.status = "completed"
                if not r.ended_at:
                    r.ended_at = now()
            c = await session.get(Call, call_id)
            if c and c.status in ("dialing", "ringing", "active"):
                c.status = "completed"
                if not c.ended_at:
                    c.ended_at = now()
            await session.commit()

        await register_local_artifacts(run_id, host.directory, org_id=org_id)
