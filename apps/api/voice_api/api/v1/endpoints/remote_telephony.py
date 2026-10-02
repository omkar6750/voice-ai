"""Twilio telephony callbacks and WebSocket Media Stream endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from voice_api.api.deps import get_session
from voice_api.core.config import get_settings
from voice_api.db.tenant_scope import bind_call_organization
from voice_api.services.call_service import (
    apply_twilio_call_status,
    apply_twilio_stream_status,
    get_by_correlation_id,
)
from voice_api.services.twilio_service import resolve_twilio_credentials
from voice_runtime.telephony.twilio import PublicTelephonyUrls
from voice_runtime.telephony.twilio_protocol import validate_twilio_signature

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
