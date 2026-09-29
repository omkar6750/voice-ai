from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from voice_api.api.v1.endpoints import calendar as calendar_endpoint
from voice_api.models import CalendarIntegration
from voice_api.services.calendar_service import (
    BusyPeriod,
    SchedulingError,
    calendar_call,
    format_local_callback_time,
    generate_slots,
    resolve_timeframe,
)


def test_tomorrow_morning_is_bounded_and_timezone_aware():
    reference = datetime(2026, 9, 25, 8, 0, tzinfo=UTC)
    window = resolve_timeframe("tomorrow morning", "Asia/Kolkata", reference=reference)
    assert window.start.isoformat() == "2026-09-26T09:00:00+05:30"
    assert window.end.isoformat() == "2026-09-26T12:00:00+05:30"


def test_explicit_time_is_a_15_minute_window():
    window = resolve_timeframe(
        "tomorrow at 10:30 AM", "Asia/Kolkata", reference=datetime(2026, 9, 25, 8, tzinfo=UTC)
    )
    assert (window.end - window.start).seconds == 900


def test_slot_engine_clips_overlaps_and_returns_small_set():
    window = resolve_timeframe(
        "tomorrow morning", "Asia/Kolkata", reference=datetime(2026, 9, 25, 8, tzinfo=UTC)
    )
    busy = [
        BusyPeriod(
            datetime(2026, 9, 26, 9, 30, tzinfo=window.start.tzinfo),
            datetime(2026, 9, 26, 10, 30, tzinfo=window.start.tzinfo),
        )
    ]
    slots = generate_slots(window, busy, limit=10)
    assert slots[0][0].hour == 9 and slots[0][0].minute == 0
    assert all(end <= window.end for _, end in slots)
    assert not any(start < busy[0].end and end > busy[0].start for start, end in slots)


def test_past_time_is_rejected():
    with pytest.raises(SchedulingError):
        resolve_timeframe(
            "today at 9 AM", "Asia/Kolkata", reference=datetime(2026, 9, 25, 8, 0, tzinfo=UTC)
        )


def test_time_without_at_prefix_uses_contact_timezone():
    window = resolve_timeframe(
        "tomorrow 10:30 AM",
        "Asia/Kolkata",
        reference=datetime(2026, 9, 25, 8, 0, tzinfo=UTC),
    )
    assert window.start.isoformat() == "2026-09-26T10:30:00+05:30"
    assert window.end.isoformat() == "2026-09-26T10:45:00+05:30"


def test_callback_confirmation_uses_portable_local_time_format():
    value = datetime(2026, 9, 26, 5, 0, tzinfo=UTC)
    assert format_local_callback_time(value, "Asia/Kolkata") == (
        "Saturday at 10:30 AM (Asia/Kolkata)"
    )


@pytest.mark.asyncio
async def test_freebusy_calendar_errors_are_not_reported_as_free(monkeypatch):
    integration = CalendarIntegration(
        id="calendar-integration",
        display_name="Team",
        calendar_id="team@example.test",
        timezone="UTC",
        scopes=[],
        status="connected",
    )

    class Request:
        def execute(self):
            return {
                "calendars": {
                    integration.calendar_id: {
                        "errors": [{"reason": "notFound"}],
                        "busy": [],
                    }
                }
            }

    class Service:
        def freebusy(self):
            return SimpleNamespace(query=lambda **_: Request())

    async def credentials(*_):
        return object()

    monkeypatch.setattr("voice_api.services.calendar_service.credentials_for", credentials)
    monkeypatch.setattr("voice_api.services.calendar_service.build", lambda *_args, **_kwargs: Service())
    with pytest.raises(SchedulingError, match="could not verify calendar availability"):
        await calendar_call(
            None,
            integration,
            "freebusy",
            start=datetime(2026, 9, 26, 9, tzinfo=UTC),
            end=datetime(2026, 9, 26, 10, tzinfo=UTC),
            timezone="UTC",
        )


@pytest.mark.asyncio
async def test_availability_provider_failure_is_not_reported_as_empty_slots(monkeypatch):
    role = SimpleNamespace(key="sales", enabled=True)
    person = SimpleNamespace(
        key="employee",
        roles=["sales"],
        enabled=True,
        calendar_integration_id="calendar-integration",
        timezone="UTC",
    )
    scheduling = SimpleNamespace(
        enabled=True,
        roles=[role],
        bookable_people=[person],
        slot_duration_minutes=15,
        minimum_notice_minutes=0,
    )
    version = SimpleNamespace(config={})
    integration = SimpleNamespace(status="connected", timezone="UTC")
    session = SimpleNamespace(get=AsyncMock(side_effect=[version, integration]))

    async def failed_freebusy(*_args, **_kwargs):
        raise SchedulingError("Google Calendar could not verify calendar availability")

    monkeypatch.setattr(
        calendar_endpoint.AgentConfig,
        "model_validate",
        lambda _config: SimpleNamespace(callback_scheduling=scheduling),
    )
    monkeypatch.setattr(calendar_endpoint, "calendar_call", failed_freebusy)
    with pytest.raises(HTTPException) as error:
        await calendar_endpoint.availability(
            calendar_endpoint.AvailabilityRequest(
                agent_version_id="agent-version",
                timeframe="tomorrow morning",
                role="sales",
            ),
            session=session,
            _=None,
        )
    assert error.value.status_code == 502
    assert "could not be checked" in error.value.detail


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["insert", "delete"])
async def test_calendar_writes_use_configured_calendar_id(monkeypatch, operation):
    integration = CalendarIntegration(
        id="calendar-integration",
        display_name="Team",
        calendar_id="team@example.test",
        timezone="UTC",
        scopes=[],
        status="connected",
    )
    calls = []

    class Request:
        def execute(self):
            return {"id": "event-123"}

    class Events:
        def insert(self, *, calendarId, body):
            calls.append(("insert", calendarId, body))
            return Request()

        def delete(self, *, calendarId, eventId):
            calls.append(("delete", calendarId, eventId))
            return Request()

    class Service:
        def events(self):
            return Events()

    async def credentials(*_):
        return object()

    monkeypatch.setattr("voice_api.services.calendar_service.credentials_for", credentials)
    monkeypatch.setattr("voice_api.services.calendar_service.build", lambda *_args, **_kwargs: Service())
    kwargs = {"event": {"summary": "Test"}} if operation == "insert" else {"event_id": "event-123"}
    await calendar_call(None, integration, operation, **kwargs)
    assert calls[0][1] == integration.calendar_id
