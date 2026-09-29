"""Google Calendar OAuth and human callback scheduling endpoints."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from voice_api.api.deps import get_session, require_legacy_owner, require_runtime_service
from voice_api.db.tenant_scope import bind_calendar_oauth_organization
from voice_api.models import (
    AgentVersion,
    CalendarIntegration,
    CalendarOAuthState,
    Callback,
    Contact,
)
from voice_api.models.common import new_id, now
from voice_api.schemas.calendar import CallbackAvailabilityResult, CallbackBookingResponse
from voice_api.services.calendar_service import (
    SCOPES,
    SchedulingError,
    _put_secret,
    calendar_call,
    format_local_callback_time,
    generate_slots,
    google_flow,
    resolve_timeframe,
    sign_slot,
    verify_slot,
)
from voice_api.services.vault_service import CredentialVault
from voice_runtime.contracts import AgentConfig

router = APIRouter(tags=["calendar"])
Session = Depends(get_session)
Operator = Depends(require_legacy_owner)
Runtime = Depends(require_runtime_service)


class CreateCalendar(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    timezone: str = "UTC"


class UpdateCalendar(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    timezone: str | None = None


class AvailabilityRequest(BaseModel):
    agent_version_id: str
    contact_id: str | None = None
    timeframe: str
    role: str
    duration_minutes: int | None = Field(default=None, ge=5, le=120)


class BookRequest(BaseModel):
    agent_version_id: str
    contact_id: str
    slot_id: str
    reason: str = Field(min_length=1, max_length=2000)


def _error(exc: Exception) -> HTTPException:
    return HTTPException(422, str(exc))


@router.get("/calendar-integrations")
async def list_calendars(session: AsyncSession = Session, _: None = Operator) -> dict:
    rows = (
        await session.scalars(
            select(CalendarIntegration).order_by(CalendarIntegration.display_name)
        )
    ).all()
    return {
        "integrations": [
            {
                "id": r.id,
                "display_name": r.display_name,
                "provider": r.provider,
                "calendar_id": r.calendar_id,
                "timezone": r.timezone,
                "status": r.status,
                "scopes": r.scopes,
                "connected_at": r.connected_at.isoformat() if r.connected_at else None,
                "last_error": r.last_error,
            }
            for r in rows
        ]
    }


@router.post("/calendar-integrations/google/connect")
async def connect_calendar(
    body: CreateCalendar, session: AsyncSession = Session, _: None = Operator
) -> dict:
    row = CalendarIntegration(
        id=new_id(),
        display_name=body.display_name,
        timezone=body.timezone,
        scopes=SCOPES,
        status="pending",
    )
    session.add(row)
    await session.flush()
    raw_state = token_urlsafe(32)
    code_verifier = token_urlsafe(64)
    encrypted_verifier = CredentialVault.from_env().encrypt(code_verifier)
    session.add(
        CalendarOAuthState(
            id=new_id(),
            state_hash=hashlib.sha256(raw_state.encode()).hexdigest(),
            calendar_integration_id=row.id,
            expires_at=now() + timedelta(minutes=10),
            pkce_verifier_ciphertext=encrypted_verifier.ciphertext,
            pkce_verifier_key_id=encrypted_verifier.key_id,
        )
    )
    try:
        url, _ = google_flow(raw_state, code_verifier=code_verifier).authorization_url(
            access_type="offline", include_granted_scopes="true", prompt="consent"
        )
    except SchedulingError as exc:
        raise _error(exc) from exc
    await session.commit()
    return {"id": row.id, "authorization_url": url}


@router.get("/calendar-integrations/google/callback")
async def oauth_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    session: AsyncSession = Session,
):
    if error:
        raise HTTPException(400, "Google authorization was denied")
    if not code or not state:
        raise HTTPException(400, "Missing OAuth callback parameters")
    state_hash = hashlib.sha256(state.encode()).hexdigest()
    await bind_calendar_oauth_organization(session, state_hash)
    state_row = await session.scalar(
        select(CalendarOAuthState)
        .where(CalendarOAuthState.state_hash == state_hash)
        .with_for_update()
    )
    if state_row is None or state_row.used_at is not None or state_row.expires_at <= now():
        raise HTTPException(400, "Invalid or expired OAuth state")
    integration = await session.get(
        CalendarIntegration, state_row.calendar_integration_id, with_for_update=True
    )
    if integration is None:
        raise HTTPException(404, "Calendar integration not found")
    if not state_row.pkce_verifier_ciphertext or not state_row.pkce_verifier_key_id:
        raise HTTPException(
            400, "OAuth session is missing PKCE state. Please reconnect Google Calendar."
        )
    try:
        code_verifier = CredentialVault.from_env().decrypt(
            state_row.pkce_verifier_ciphertext, state_row.pkce_verifier_key_id
        )
        flow = google_flow(state, code_verifier=code_verifier)
        flow.fetch_token(code=code)
        credentials = flow.credentials
        await _put_secret(session, integration.id, "access_token", credentials.token)
        if credentials.refresh_token:
            await _put_secret(session, integration.id, "refresh_token", credentials.refresh_token)
        integration.status, integration.connected_at, integration.token_expires_at = (
            "connected",
            now(),
            credentials.expiry,
        )
        integration.scopes = list(credentials.scopes or SCOPES)
        integration.last_error = None
        state_row.used_at = now()
        state_row.pkce_verifier_ciphertext = None
        state_row.pkce_verifier_key_id = None
        await session.commit()
    except Exception as exc:
        integration.status, integration.last_error = "error", f"OAuth failed: {type(exc).__name__}"
        logger.error(
            "Google Calendar OAuth failed integration={} type={} error={} description={}",
            integration.id,
            type(exc).__name__,
            getattr(exc, "error", None),
            getattr(exc, "description", None),
        )
        await session.commit()
        raise HTTPException(502, "Google authorization could not be completed") from exc
    return RedirectResponse("/integrations?calendar=connected")


@router.post("/calendar-integrations/{integration_id}/reconnect")
async def reconnect(
    integration_id: str, session: AsyncSession = Session, _: None = Operator
) -> dict:
    integration = await session.get(CalendarIntegration, integration_id)
    if integration is None:
        raise HTTPException(404, "Calendar integration not found")
    raw_state = token_urlsafe(32)
    code_verifier = token_urlsafe(64)
    encrypted_verifier = CredentialVault.from_env().encrypt(code_verifier)
    session.add(
        CalendarOAuthState(
            id=new_id(),
            state_hash=hashlib.sha256(raw_state.encode()).hexdigest(),
            calendar_integration_id=integration.id,
            expires_at=now() + timedelta(minutes=10),
            pkce_verifier_ciphertext=encrypted_verifier.ciphertext,
            pkce_verifier_key_id=encrypted_verifier.key_id,
        )
    )
    try:
        url, _ = google_flow(raw_state, code_verifier=code_verifier).authorization_url(
            access_type="offline", include_granted_scopes="true", prompt="consent"
        )
    except SchedulingError as exc:
        raise _error(exc) from exc
    await session.commit()
    return {"authorization_url": url}


@router.patch("/calendar-integrations/{integration_id}")
async def rename_calendar(
    integration_id: str, body: UpdateCalendar, session: AsyncSession = Session, _: None = Operator
) -> dict:
    row = await session.get(CalendarIntegration, integration_id, with_for_update=True)
    if row is None:
        raise HTTPException(404, "Calendar integration not found")
    row.display_name = body.display_name.strip()
    if body.timezone:
        row.timezone = body.timezone
    await session.commit()
    return {
        "id": row.id,
        "display_name": row.display_name,
        "timezone": row.timezone,
        "status": row.status,
    }


@router.delete("/calendar-integrations/{integration_id}", status_code=204)
async def disconnect(
    integration_id: str, session: AsyncSession = Session, _: None = Operator
) -> None:
    row = await session.get(CalendarIntegration, integration_id, with_for_update=True)
    if row is None:
        raise HTTPException(404, "Calendar integration not found")
    row.status, row.revoked_at = "disconnected", now()
    await session.commit()


@router.post(
    "/callback-scheduling/availability", response_model=CallbackAvailabilityResult
)
async def availability(
    body: AvailabilityRequest, session: AsyncSession = Session, _: None = Runtime
) -> dict:
    version = await session.get(AgentVersion, body.agent_version_id)
    if version is None:
        raise HTTPException(404, "Agent version not found")
    requested_timeframe = body.timeframe
    if not body.contact_id:
        return {
            "status": "timezone_required",
            "requested_timeframe": requested_timeframe,
            "message": "The caller's timezone is unknown. Ask for their timezone before checking callback availability.",
        }
    contact = await session.get(Contact, body.contact_id)
    if contact is None:
        return {
            "status": "contact_unavailable",
            "requested_timeframe": requested_timeframe,
            "message": "The callback contact could not be found.",
        }
    if not contact.timezone:
        return {
            "status": "timezone_required",
            "requested_timeframe": requested_timeframe,
            "message": "The caller's timezone is unknown. Ask for their timezone before checking callback availability.",
        }
    config = AgentConfig.model_validate(version.config).callback_scheduling
    role = next((r for r in config.roles if r.key == body.role), None)
    if not config.enabled or role is None or not role.enabled:
        return {
            "status": "configuration_error",
            "requested_timeframe": requested_timeframe,
            "message": "That callback role is not enabled for this agent.",
        }
    candidates = [p for p in config.bookable_people if p.enabled and body.role in p.roles]
    if not candidates:
        return {
            "status": "configuration_error",
            "requested_timeframe": requested_timeframe,
            "message": "No enabled bookable person is configured for this callback role.",
        }
    try:
        window = resolve_timeframe(body.timeframe, contact.timezone)
    except SchedulingError as exc:
        status = (
            "configuration_error"
            if str(exc).startswith("Unknown timezone:")
            else "invalid_timeframe"
        )
        message = (
            "The saved contact timezone is invalid; ask the operator to correct it."
            if status == "configuration_error"
            else str(exc)
        )
        return {"status": status, "requested_timeframe": requested_timeframe, "message": message}

    candidate_slots = []
    failures = []
    checked_calendars = 0
    connected_calendars = 0
    for person_order, person in enumerate(candidates):
        integration = await session.get(CalendarIntegration, person.calendar_integration_id)
        if integration is None or integration.status != "connected":
            failures.append("A configured calendar is disconnected.")
            continue
        connected_calendars += 1
        try:
            busy = await calendar_call(
                session,
                integration,
                "freebusy",
                start=window.start,
                end=window.end,
                timezone=contact.timezone,
            )
        except SchedulingError:
            failures.append("A configured calendar's availability could not be checked.")
            continue
        except Exception:
            logger.exception("Unexpected callback availability failure for calendar {}", integration.id)
            failures.append("A configured calendar's availability could not be checked.")
            continue
        checked_calendars += 1
        for start, end in generate_slots(
            window,
            busy,
            duration_minutes=body.duration_minutes or config.slot_duration_minutes,
            minimum_notice_minutes=config.minimum_notice_minutes,
            limit=3,
        ):
            payload = {
                "person": person.key,
                "integration": integration.id,
                "role": body.role,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "timezone": contact.timezone,
                "window_start": window.start.isoformat(),
                "window_end": window.end.isoformat(),
                "timeframe": body.timeframe,
                "expires_at": (datetime.now(UTC) + timedelta(minutes=10)).isoformat(),
                "agent_version_id": body.agent_version_id,
                "contact_id": body.contact_id,
            }
            candidate_slots.append(
                (
                    start.astimezone(UTC),
                    person_order,
                    end.astimezone(UTC),
                    {
                        "slot_id": sign_slot(payload),
                        "display": format_local_callback_time(start, contact.timezone),
                    },
                )
            )
    if checked_calendars == 0:
        status = "calendar_unavailable" if connected_calendars == 0 else "availability_check_failed"
        return {
            "status": status,
            "requested_timeframe": requested_timeframe,
            "message": "No configured callback calendar could be checked. Please try again later or contact support.",
        }

    candidate_slots.sort(key=lambda item: (item[0], item[1]))
    slots, seen_intervals = [], set()
    for start_utc, _person_order, end_utc, slot in candidate_slots:
        interval = (start_utc, end_utc)
        if interval in seen_intervals:
            continue
        seen_intervals.add(interval)
        slots.append(slot)
        if len(slots) == 3:
            break
    partial = bool(failures)
    return {
        "status": (
            "partial_availability"
            if partial
            else "available"
            if slots
            else "no_availability"
        ),
        "requested_timeframe": requested_timeframe,
        "slots": slots,
        "message": (
            "Some calendars could not be checked; results may be incomplete."
            if partial
            else None
            if slots
            else "No callback slots are available in the requested window."
        ),
        "warnings": list(dict.fromkeys(failures)),
    }


@router.post("/callback-scheduling/book", response_model=CallbackBookingResponse)
async def book(body: BookRequest, session: AsyncSession = Session, _: None = Runtime) -> dict:
    try:
        payload = verify_slot(body.slot_id)
    except SchedulingError as exc:
        raise _error(exc) from exc
    if (
        payload.get("agent_version_id") != body.agent_version_id
        or payload.get("contact_id") != body.contact_id
    ):
        raise HTTPException(409, "Callback slot does not belong to this conversation")
    integration = await session.get(CalendarIntegration, payload["integration"])
    contact = await session.get(Contact, body.contact_id)
    if integration is None or integration.status != "connected" or contact is None:
        raise HTTPException(409, "Calendar or contact is unavailable")
    if not contact.timezone or contact.timezone != payload.get("timezone"):
        raise HTTPException(409, "Contact timezone changed; check callback availability again")
    start, end = datetime.fromisoformat(payload["start"]), datetime.fromisoformat(payload["end"])
    try:
        busy = await calendar_call(
            session, integration, "freebusy", start=start, end=end, timezone=payload["timezone"]
        )
    except SchedulingError as exc:
        raise HTTPException(502, "Google Calendar availability could not be checked") from exc
    if busy:
        return {
            "status": "slot_conflict",
            "message": "That slot was just taken. Please check availability again.",
        }
    callback = Callback(
        id=new_id(),
        request_key=f"human:{new_id()}",
        contact_id=body.contact_id,
        agent_version_id=body.agent_version_id,
        due_at=start,
        timezone=payload["timezone"],
        original_phrase=payload.get("timeframe", "callback"),
        status="scheduled",
        callback_mode="human",
        requested_window_start=datetime.fromisoformat(payload["window_start"]),
        requested_window_end=datetime.fromisoformat(payload["window_end"]),
        scheduled_start=start,
        scheduled_end=end,
        role_key=payload["role"],
        bookable_person_key=payload["person"],
        calendar_integration_id=integration.id,
        reason=body.reason,
    )
    session.add(callback)
    await session.flush()
    event = {
        "summary": f"Callback — {contact.name}",
        "description": f"Scheduled by Voice AI\nReason: {body.reason}\nContact: {contact.name}\nPhone: {contact.phone_number}\nCallback ID: {callback.id}",
        "start": {"dateTime": start.isoformat(), "timeZone": payload["timezone"]},
        "end": {"dateTime": end.isoformat(), "timeZone": payload["timezone"]},
        "transparency": "opaque",
        "extendedProperties": {"private": {"voice_ai_callback_id": callback.id}},
    }
    try:
        created = await calendar_call(session, integration, "insert", event=event)
    except Exception as exc:
        await session.rollback()
        raise HTTPException(502, "Google Calendar event could not be created") from exc
    callback.calendar_event_id = created.get("id")
    try:
        await session.commit()
    except Exception as exc:
        await session.rollback()
        if callback.calendar_event_id:
            try:
                await calendar_call(
                    session, integration, "delete", event_id=callback.calendar_event_id
                )
            except Exception:
                integration.last_error = "Calendar event created but callback persistence failed"
                await session.commit()
        raise HTTPException(500, "Callback could not be persisted after calendar booking") from exc
    return {
        "status": "confirmed",
        "callback_id": callback.id,
        "scheduled_time": format_local_callback_time(start, payload["timezone"]),
        "duration_minutes": int((end - start).total_seconds() / 60),
    }
