"""Deterministic callback scheduling and Google Calendar integration."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from voice_api.core.config import get_settings
from voice_api.models import CalendarIntegration, CalendarIntegrationSecret
from voice_api.models.common import new_id
from voice_api.services.vault_service import CredentialVault

SCOPES = [
    "https://www.googleapis.com/auth/calendar.freebusy",
    "https://www.googleapis.com/auth/calendar.events",
]
DAYPARTS = {"morning": (9, 12), "afternoon": (12, 17), "evening": (17, 20)}


@dataclass(frozen=True)
class TimeWindow:
    original: str
    start: datetime
    end: datetime
    timezone: str


@dataclass(frozen=True)
class BusyPeriod:
    start: datetime
    end: datetime


class SchedulingError(ValueError):
    pass


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise SchedulingError(f"Unknown timezone: {name}") from exc


def resolve_timeframe(
    phrase: str, timezone: str, *, reference: datetime | None = None
) -> TimeWindow:
    """Resolve caller language into one bounded, timezone-aware window."""
    text = " ".join(phrase.lower().strip().split())
    if not text:
        raise SchedulingError("A callback timeframe is required")
    zone = _zone(timezone)
    current = (reference or datetime.now(UTC)).astimezone(zone)
    day_offset = 0
    if "day after tomorrow" in text:
        day_offset, text = 2, text.replace("day after tomorrow", "")
    elif "tomorrow" in text:
        day_offset, text = 1, text.replace("tomorrow", "")
    elif "today" in text:
        text = text.replace("today", "")
    else:
        weekday = None
        for idx, name in enumerate(
            ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
        ):
            if name in text:
                weekday = idx
                text = text.replace("next " + name, "").replace(name, "")
                delta = (idx - current.weekday()) % 7
                day_offset = delta or 7 if "next" in phrase.lower() else delta
                break
        if weekday is None and (match := re.search(r"in (\d+) hours?", text)):
            start = current + timedelta(hours=int(match.group(1)))
            end = start + timedelta(minutes=15)
            return TimeWindow(phrase, start, end, timezone)
        if weekday is None:
            raise SchedulingError("Could not understand the requested callback timeframe")
    date = (current + timedelta(days=day_offset)).date()
    remainder = text.strip()
    if match := re.search(
        r"(?:(?:at|after)\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", remainder
    ):
        hour, minute, meridiem = int(match.group(1)), int(match.group(2) or 0), match.group(3)
        if minute > 59 or (meridiem and not 1 <= hour <= 12):
            raise SchedulingError("The requested callback time is invalid")
        if meridiem == "pm" and hour < 12:
            hour += 12
        if meridiem == "am" and hour == 12:
            hour = 0
        if hour > 23:
            raise SchedulingError("The requested callback time is invalid")
        start = datetime(date.year, date.month, date.day, hour, minute, tzinfo=zone)
        end = start + timedelta(minutes=15)
    else:
        part = next((key for key in DAYPARTS if key in remainder), None)
        if part:
            begin, finish = DAYPARTS[part]
        else:
            begin, finish = 9, 17
        start = datetime(date.year, date.month, date.day, begin, tzinfo=zone)
        end = datetime(date.year, date.month, date.day, finish, tzinfo=zone)
    if end <= current:
        raise SchedulingError("The requested callback time is already past")
    return TimeWindow(phrase, start, end, timezone)


def format_local_callback_time(value: datetime, timezone: str) -> str:
    """Format a callback time consistently on Windows and POSIX hosts."""
    local = value.astimezone(_zone(timezone))
    hour = local.hour % 12 or 12
    meridiem = "AM" if local.hour < 12 else "PM"
    return f"{local:%A} at {hour}:{local.minute:02d} {meridiem} ({timezone})"


def generate_slots(
    window: TimeWindow,
    busy: list[BusyPeriod],
    *,
    duration_minutes: int = 15,
    minimum_notice_minutes: int = 0,
    limit: int = 3,
) -> list[tuple[datetime, datetime]]:
    if duration_minutes < 1:
        raise SchedulingError("Duration must be positive")
    start = window.start
    if minimum_notice_minutes:
        start = max(
            start,
            datetime.now(UTC).astimezone(start.tzinfo) + timedelta(minutes=minimum_notice_minutes),
        )
    start = start.replace(
        minute=(start.minute // duration_minutes) * duration_minutes, second=0, microsecond=0
    )
    if start < window.start:
        start += timedelta(minutes=duration_minutes)
    busy_sorted = sorted(busy, key=lambda item: item.start)
    result = []
    while start + timedelta(minutes=duration_minutes) <= window.end and len(result) < limit:
        end = start + timedelta(minutes=duration_minutes)
        if not any(start < item.end and end > item.start for item in busy_sorted):
            result.append((start, end))
        start += timedelta(minutes=duration_minutes)
    return result


def _secret(value: str) -> dict[str, str]:
    return CredentialVault.from_env().encrypt(value).__dict__


async def _secret_value(session: AsyncSession, integration_id: str, name: str) -> str | None:
    row = await session.scalar(
        select(CalendarIntegrationSecret).where(
            CalendarIntegrationSecret.calendar_integration_id == integration_id,
            CalendarIntegrationSecret.name == name,
        )
    )
    if row is None:
        return None
    return CredentialVault.from_env().decrypt(row.ciphertext, row.key_id)


async def _put_secret(session: AsyncSession, integration_id: str, name: str, value: str) -> None:
    encrypted = _secret(value)
    row = await session.scalar(
        select(CalendarIntegrationSecret).where(
            CalendarIntegrationSecret.calendar_integration_id == integration_id,
            CalendarIntegrationSecret.name == name,
        )
    )
    if row is None:
        session.add(
            CalendarIntegrationSecret(
                id=new_id(), calendar_integration_id=integration_id, name=name, **encrypted
            )
        )
    else:
        row.ciphertext, row.key_id = encrypted["ciphertext"], encrypted["key_id"]


def google_flow(state: str | None = None, *, code_verifier: str | None = None) -> Flow:
    settings = get_settings()
    if not settings.google_calendar_client_id or not settings.google_calendar_client_secret:
        raise SchedulingError("Google Calendar OAuth is not configured")
    config = {
        "web": {
            "client_id": settings.google_calendar_client_id,
            "client_secret": settings.google_calendar_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    flow = Flow.from_client_config(
        config,
        scopes=SCOPES,
        state=state,
        code_verifier=code_verifier,
        autogenerate_code_verifier=False,
    )
    flow.redirect_uri = settings.google_calendar_redirect_uri
    return flow


async def credentials_for(session: AsyncSession, integration: CalendarIntegration) -> Credentials:
    token = await _secret_value(session, integration.id, "access_token")
    refresh = await _secret_value(session, integration.id, "refresh_token")
    if not refresh:
        raise SchedulingError("Calendar integration needs to be connected again")
    settings = get_settings()
    creds = Credentials(
        token=token,
        refresh_token=refresh,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_calendar_client_id,
        client_secret=settings.google_calendar_client_secret,
        scopes=integration.scopes or SCOPES,
    )
    if creds.expired:
        try:
            creds.refresh(Request())
        except Exception as exc:
            integration.status, integration.last_error = "error", "Google token refresh failed"
            raise SchedulingError("Google Calendar credentials are no longer valid") from exc
        await _put_secret(session, integration.id, "access_token", creds.token)
        integration.token_expires_at = creds.expiry
        await session.flush()
    return creds


async def calendar_call(
    session: AsyncSession, integration: CalendarIntegration, operation: str, **kwargs: Any
) -> Any:
    creds = await credentials_for(session, integration)
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)
    if operation == "freebusy":
        body = {
            "timeMin": kwargs["start"].isoformat(),
            "timeMax": kwargs["end"].isoformat(),
            "timeZone": kwargs["timezone"],
            "items": [{"id": integration.calendar_id or "primary"}],
        }
        try:
            response = service.freebusy().query(body=body).execute()
        except Exception as exc:
            raise SchedulingError("Google Calendar could not verify calendar availability") from exc
        calendars = response.get("calendars", {})
        calendar_id = integration.calendar_id or "primary"
        if calendar_id not in calendars:
            raise SchedulingError("Google Calendar could not verify calendar availability")
        calendar = calendars[calendar_id]
        if calendar.get("errors"):
            raise SchedulingError("Google Calendar could not verify calendar availability")
        try:
            return [
                BusyPeriod(
                    datetime.fromisoformat(item["start"]),
                    datetime.fromisoformat(item["end"]),
                )
                for item in calendar.get("busy", [])
            ]
        except (KeyError, TypeError, ValueError) as exc:
            raise SchedulingError("Google Calendar returned invalid availability data") from exc
    if operation == "insert":
        return service.events().insert(
            calendarId=integration.calendar_id or "primary", body=kwargs["event"]
        ).execute()
    if operation == "delete":
        return service.events().delete(
            calendarId=integration.calendar_id or "primary", eventId=kwargs["event_id"]
        ).execute()
    raise SchedulingError("Unsupported Google Calendar operation")


def sign_slot(payload: dict) -> str:
    raw = (
        base64.urlsafe_b64encode(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        )
        .decode()
        .rstrip("=")
    )
    key = (
        get_settings().integration_active_key
        or get_settings().operator_token
        or "development-slot-key"
    ).encode()
    signature = hmac.new(key, raw.encode(), hashlib.sha256).hexdigest()
    return f"{raw}.{signature}"


def verify_slot(value: str) -> dict:
    try:
        raw, signature = value.split(".", 1)
    except ValueError as exc:
        raise SchedulingError("Invalid callback slot") from exc
    key = (
        get_settings().integration_active_key
        or get_settings().operator_token
        or "development-slot-key"
    ).encode()
    if not hmac.compare_digest(signature, hmac.new(key, raw.encode(), hashlib.sha256).hexdigest()):
        raise SchedulingError("Invalid callback slot")
    payload = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
    if datetime.fromisoformat(payload["expires_at"]) <= datetime.now(UTC):
        raise SchedulingError("Callback slot has expired")
    return payload
