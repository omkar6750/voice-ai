"""Exactly-once-attempt Twilio call dispatch and callback reconciliation."""

from __future__ import annotations

import asyncio
import re
from typing import Any
from urllib.parse import urlsplit

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from twilio.base.exceptions import TwilioRestException
from voice_runtime.telephony.twilio import PublicTelephonyUrls, TwilioCallController

from voice_api.models import Call, Run
from voice_api.models.common import now
from voice_api.services.twilio_service import resolve_twilio_credentials

DISPATCH_TIMEOUT_SECS = 15.0
_PRE_CALLBACK_STATUSES = {"queued", "dialing"}
_CALL_SID_PATTERN = re.compile(r"CA[0-9a-fA-F]{32}\Z")


def _canonical_public_base_url(value: str | None) -> str:
    if not value or any(char.isspace() for char in value):
        raise HTTPException(422, "Twilio dispatch requires a canonical HTTPS public URL")
    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except ValueError:
        raise HTTPException(422, "Twilio dispatch requires a canonical HTTPS public URL") from None
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or "@" in parsed.netloc
        or parsed.query
        or parsed.fragment
        or "?" in value
        or "#" in value
        or "\\" in parsed.path
    ):
        raise HTTPException(422, "Twilio dispatch requires a canonical HTTPS public URL")
    return value.rstrip("/")


def _has_callback_evidence(call: Call) -> bool:
    metadata = dict(call.provider_metadata or {})
    return bool(
        call.provider_call_id
        or metadata.get("twilio_status")
        or call.status not in _PRE_CALLBACK_STATUSES
    )


def validate_twilio_dispatch_settings(settings: Any) -> str:
    """Reject invalid deployment settings before creating a queued request."""
    public_base_url = _canonical_public_base_url(settings.public_base_url)
    if not settings.runtime_service_token:
        raise HTTPException(422, "Twilio dispatch requires the runtime service token")
    return public_base_url


async def _locked_rows(
    session: AsyncSession, call_id: str, run_id: str
) -> tuple[Call | None, Run | None]:
    call = await session.get(Call, call_id, with_for_update=True, populate_existing=True)
    if call is None:
        return None, None
    run = await session.get(Run, run_id, with_for_update=True, populate_existing=True)
    return call, run


async def _record_uncertain(
    session: AsyncSession,
    call_id: str,
    run_id: str,
    *,
    reason: str,
    definite_rejection: bool = False,
) -> bool:
    call, run = await _locked_rows(session, call_id, run_id)
    if call is None or run is None:
        await session.commit()
        return False
    metadata = dict(call.provider_metadata or {})
    callback_seen = _has_callback_evidence(call)
    if definite_rejection and not callback_seen and run.status == "queued":
        call.status = "failed"
        call.ended_at = call.ended_at or now()
        run.status = "failed"
        run.ended_at = run.ended_at or now()
        metadata["twilio_dispatch_state"] = "rejected"
        metadata["twilio_dispatch_error"] = "provider_rejected"
    else:
        metadata["twilio_dispatch_state"] = (
            "uncertain_callback_seen" if callback_seen else "uncertain"
        )
        metadata["twilio_dispatch_error"] = reason
        # Keep the established lifecycle states. The durable attempt fence
        # prevents redial while late callbacks can still claim the queued Run.
    call.provider_metadata = metadata
    await session.commit()
    return metadata["twilio_dispatch_state"] == "rejected"


def _is_definite_rejection(error: BaseException) -> bool:
    status = getattr(error, "status", None)
    return (
        isinstance(error, TwilioRestException) and isinstance(status, int) and 400 <= status < 500
    )


async def dispatch_twilio_call(
    session: AsyncSession,
    call: Call,
    run: Run,
    settings: Any,
) -> tuple[Call, Run]:
    """Fence one Twilio create attempt, then reconcile it with racing callbacks."""
    public_base_url = validate_twilio_dispatch_settings(settings)

    _, credentials = await resolve_twilio_credentials(session, call.telephony_connection_id)

    try:
        urls = PublicTelephonyUrls(public_base_url)
        controller = TwilioCallController(credentials)
    except Exception:
        # Client construction is local setup; leave the queued call eligible.
        raise HTTPException(503, "Twilio dispatch setup is unavailable") from None

    locked_call, locked_run = await _locked_rows(session, call.id, run.id)
    if locked_call is None or locked_run is None:
        raise HTTPException(404, "Call or run not found")
    metadata = dict(locked_call.provider_metadata or {})
    if (
        locked_call.provider != "twilio"
        or locked_call.run_id != locked_run.id
        or locked_call.status != "queued"
        or locked_run.status != "queued"
        or locked_call.provider_call_id is not None
        or metadata.get("twilio_dispatch_attempted")
    ):
        raise HTTPException(409, "Twilio call is not eligible for dispatch")

    metadata.update(
        {
            "twilio_dispatch_attempted": True,
            "twilio_dispatch_state": "dispatching",
            "twilio_dispatch_attempts": 1,
        }
    )
    locked_call.provider_metadata = metadata
    locked_call.status = "dialing"
    await session.commit()

    try:
        async with asyncio.timeout(DISPATCH_TIMEOUT_SECS):
            call_sid = await controller.dial(
                to=locked_call.target_snapshot,
                from_number=locked_call.from_number,
                media_ws_url=urls.twilio_media(locked_call.correlation_id),
                status_callback_url=urls.twilio_call_status(locked_call.correlation_id),
                stream_status_callback_url=urls.twilio_stream_status(locked_call.correlation_id),
                correlation_id=locked_call.correlation_id,
                run_id=locked_run.id,
            )
    except asyncio.CancelledError:
        await _record_uncertain(session, call.id, run.id, reason="cancelled_during_create")
        raise
    except TimeoutError:
        await _record_uncertain(session, call.id, run.id, reason="create_timeout")
        raise HTTPException(502, "Twilio call dispatch outcome is uncertain") from None
    except Exception as error:
        definite = _is_definite_rejection(error)
        rejected = await _record_uncertain(
            session,
            call.id,
            run.id,
            reason="provider_rejected" if definite else "create_failed_uncertain",
            definite_rejection=definite,
        )
        raise HTTPException(
            502,
            "Twilio rejected the call request"
            if rejected
            else "Twilio call dispatch outcome is uncertain",
        ) from None

    if not isinstance(call_sid, str) or _CALL_SID_PATTERN.fullmatch(call_sid) is None:
        await _record_uncertain(session, call.id, run.id, reason="invalid_call_sid")
        raise HTTPException(502, "Twilio call dispatch outcome is uncertain")

    locked_call, locked_run = await _locked_rows(session, call.id, run.id)
    if locked_call is None or locked_run is None:
        raise HTTPException(502, "Twilio call dispatch outcome is uncertain")
    if locked_call.provider_call_id not in (None, call_sid):
        metadata = dict(locked_call.provider_metadata or {})
        metadata["twilio_dispatch_state"] = "uncertain_sid_conflict"
        metadata["twilio_dispatch_error"] = "callback_sid_conflict"
        locked_call.provider_metadata = metadata
        await session.commit()
        raise HTTPException(502, "Twilio call dispatch outcome is uncertain")

    callback_seen = _has_callback_evidence(locked_call)
    locked_call.provider_call_id = locked_call.provider_call_id or call_sid
    metadata = dict(locked_call.provider_metadata or {})
    metadata["twilio_dispatch_state"] = "callback_confirmed" if callback_seen else "accepted"
    metadata.pop("twilio_dispatch_error", None)
    locked_call.provider_metadata = metadata
    await session.commit()
    return locked_call, locked_run
