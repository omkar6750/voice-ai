"""Twilio telephony callbacks and WebSocket Media Stream endpoint."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request, Response, WebSocket
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.websockets import WebSocketState
from voice_api.api.deps import get_session
from voice_api.core.config import get_settings
from voice_api.db.session import SessionFactory
from voice_api.db.tenant_scope import bind_call_organization
from voice_api.services.call_service import (
    apply_twilio_call_status,
    apply_twilio_stream_status,
    claim_twilio_media,
    get_by_correlation_id,
)
from voice_api.services.provider_credentials import settings_for_run
from voice_api.services.twilio_runtime_service import (
    finalize_twilio_startup_failure,
    run_twilio_pipeline,
)
from voice_api.services.twilio_service import resolve_twilio_credentials
from voice_runtime.execution.termination import CallTermination
from voice_runtime.telephony.twilio import PublicTelephonyUrls
from voice_runtime.telephony.twilio_protocol import read_twilio_start, validate_twilio_signature
from voice_runtime.telephony.twilio_rest import TwilioRestCall
from voice_runtime.telephony.twilio_session import (
    ManagedTwilioSerializer,
    ManagedTwilioTransport,
    TwilioMediaSession,
)

router = APIRouter(prefix="/telephony", tags=["telephony"])
Session = Depends(get_session)


async def _authenticated_callback(session, correlation_id, request, *, stream: bool):
    await bind_call_organization(session, correlation_id)
    call = await get_by_correlation_id(session, correlation_id)
    if call is None or call.provider != "twilio":
        raise HTTPException(404, "Call not found")
    _, credentials = await resolve_twilio_credentials(
        session, call.telephony_connection_id, require_enabled=False
    )
    form = await request.form()
    public_base_url = get_settings().public_base_url
    if not public_base_url:
        raise HTTPException(503, "Twilio public URL is not configured")
    urls = PublicTelephonyUrls(public_base_url)
    url = (
        urls.twilio_stream_status(correlation_id)
        if stream
        else urls.twilio_call_status(correlation_id)
    )
    if not validate_twilio_signature(
        credentials.auth_token,
        url,
        form,
        request.headers.get("x-twilio-signature", ""),
    ):
        raise HTTPException(403, "Invalid Twilio signature or public URL configuration")
    if (
        len(form.getlist("AccountSid")) != 1
        or len(form.getlist("CallSid")) != 1
        or form.get("AccountSid") != credentials.account_sid
        or not form.get("CallSid")
        or (call.provider_call_id and form.get("CallSid") != call.provider_call_id)
    ):
        raise HTTPException(409, "Twilio call identity mismatch")
    return call, form


@router.post("/twilio/call-status/{correlation_id}")
async def twilio_call_status(
    correlation_id: str,
    request: Request,
    session: AsyncSession = Session,
) -> Response:
    call, form = await _authenticated_callback(session, correlation_id, request, stream=False)
    raw_sequence = form.get("SequenceNumber")
    sequence = None
    if raw_sequence is not None:
        if (
            len(form.getlist("SequenceNumber")) != 1
            or not isinstance(raw_sequence, str)
            or not 1 <= len(raw_sequence) <= 10
            or not raw_sequence.isascii()
            or not raw_sequence.isdigit()
        ):
            raise HTTPException(422, "Invalid Twilio SequenceNumber")
        sequence = int(raw_sequence)
    try:
        await apply_twilio_call_status(
            session,
            call=call,
            twilio_status=form.get("CallStatus"),
            sequence_number=sequence,
            provider_call_id=form.get("CallSid"),
        )
    except ValueError:
        raise HTTPException(409, "Twilio call identity mismatch") from None
    return Response(status_code=204)


@router.post("/twilio/stream-status/{correlation_id}")
async def twilio_stream_status(
    correlation_id: str,
    request: Request,
    session: AsyncSession = Session,
) -> Response:
    call, form = await _authenticated_callback(session, correlation_id, request, stream=True)
    try:
        await apply_twilio_stream_status(
            session,
            call=call,
            stream_sid=form.get("StreamSid"),
            event=form.get("StatusCallbackEvent"),
            error=form.get("StreamError"),
            provider_call_id=form.get("CallSid"),
        )
    except ValueError:
        raise HTTPException(409, "Twilio call identity mismatch") from None
    return Response(status_code=204)


@router.websocket("/twilio/media/{correlation_id}")
async def twilio_media_endpoint(websocket: WebSocket, correlation_id: str) -> None:
    async with SessionFactory() as session:
        try:
            await bind_call_organization(session, correlation_id)
        except HTTPException:
            await websocket.close(code=1008)
            return
        call = await get_by_correlation_id(session, correlation_id)
        if (
            call is None
            or call.provider != "twilio"
            or not call.telephony_connection_id
            or not call.run_id
            or call.status in {"completed", "failed", "canceled"}
        ):
            await websocket.close(code=1008)
            return
        call_id, run_id = call.id, call.run_id
        provider_call_id = call.provider_call_id
        existing_stream_sid = (call.provider_metadata or {}).get("stream_sid")
        try:
            _, credentials = await resolve_twilio_credentials(
                session, call.telephony_connection_id, require_enabled=True
            )
        except HTTPException:
            await websocket.close(code=1008)
            return

    settings = get_settings()
    try:
        canonical_url = PublicTelephonyUrls(settings.public_base_url or "").twilio_media(
            correlation_id
        )
    except ValueError:
        await websocket.close(code=1008)
        return
    if not validate_twilio_signature(
        credentials.auth_token,
        canonical_url,
        {},
        websocket.headers.get("x-twilio-signature", ""),
        websocket=True,
    ):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    try:
        call_sid, stream_sid = await read_twilio_start(
            websocket,
            account_sid=credentials.account_sid,
            expected_call_sid=provider_call_id,
            expected_stream_sid=existing_stream_sid,
            run_id=run_id,
            correlation_id=correlation_id,
        )
    except Exception:
        await websocket.close(code=1008)
        return
    # Construct local resources before owning a Run; a rejected duplicate only
    # closes its unused REST client and never hangs up the legitimate stream.
    rest = TwilioRestCall(credentials, call_sid)
    media = TwilioMediaSession(stream_sid, CallTermination(), websocket.send_json, rest)
    try:
        async with SessionFactory() as session:
            await bind_call_organization(session, correlation_id)
            snapshot = await claim_twilio_media(
                session,
                call_id=call_id,
                run_id=run_id,
                provider_call_id=call_sid,
                stream_sid=stream_sid,
            )
    except BaseException:
        await rest.aclose()
        raise
    if snapshot is None:
        await rest.aclose()
        await websocket.close(code=1008)
        return

    try:
        serializer = ManagedTwilioSerializer(
            media,
            sample_rate=snapshot.get("audio", {}).get("sample_rate", 16000),
        )
        transport = ManagedTwilioTransport(
            websocket,
            FastAPIWebsocketParams(
                audio_in_enabled=True,
                audio_out_enabled=True,
                add_wav_header=False,
                serializer=serializer,
                # Twilio authenticates by signature, not a browser Origin.
                allowed_origins=[],
            ),
        )

        @transport.event_handler("on_client_disconnected")
        async def on_client_disconnected(_transport, _ws):
            media.disconnected()

        await run_twilio_pipeline(
            call_id=call_id,
            run_id=run_id,
            snapshot=snapshot,
            transport=transport,
            media=media,
            settings=await settings_for_run(run_id, settings),
            auth_token=credentials.auth_token,
        )
    except asyncio.CancelledError:
        await finalize_twilio_startup_failure(
            call_id=call_id, run_id=run_id, media=media, cancelled=True
        )
        raise
    except Exception:
        await finalize_twilio_startup_failure(call_id=call_id, run_id=run_id, media=media)
    finally:
        # Last-resort owner even if transport/client construction failed. Repeated
        # calls join the same close task; they never send a second REST hangup.
        await media.close()
        if websocket.application_state != WebSocketState.DISCONNECTED:
            await websocket.close()
