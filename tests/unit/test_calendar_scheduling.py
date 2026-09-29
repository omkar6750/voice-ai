from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from voice_api.api.v1.endpoints import calendar as calendar_endpoint
from voice_api.models import CalendarIntegration
from voice_api.services import calendar_service
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


def test_invalid_clock_time_is_returned_as_scheduling_error():
    with pytest.raises(SchedulingError, match="time is invalid"):
        resolve_timeframe(
            "tomorrow at 25:90",
            "Asia/Kolkata",
            reference=datetime(2026, 9, 25, 8, 0, tzinfo=UTC),
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
    contact = SimpleNamespace(timezone="Asia/Kolkata")
    integration = SimpleNamespace(status="connected", timezone="UTC")
    session = SimpleNamespace(get=AsyncMock(side_effect=[version, contact, integration]))

    async def failed_freebusy(*_args, **_kwargs):
        raise SchedulingError("Google Calendar could not verify calendar availability")

    monkeypatch.setattr(
        calendar_endpoint.AgentConfig,
        "model_validate",
        lambda _config: SimpleNamespace(callback_scheduling=scheduling),
    )
    monkeypatch.setattr(calendar_endpoint, "calendar_call", failed_freebusy)
    result = await calendar_endpoint.availability(
        calendar_endpoint.AvailabilityRequest(
            agent_version_id="agent-version",
            contact_id="contact-1",
            timeframe="tomorrow morning",
            role="sales",
        ),
        session=session,
        _=None,
    )
    assert result["status"] == "availability_check_failed"
    assert "could be checked" in result["message"]


@pytest.mark.asyncio
async def test_availability_uses_contact_timezone_and_skips_disconnected_person(monkeypatch):
    monkeypatch.setattr(
        calendar_service,
        "get_settings",
        lambda: SimpleNamespace(callback_slot_signing_key="test-key"),
    )
    role = SimpleNamespace(key="sales", enabled=True)
    people = [
        SimpleNamespace(
            key=f"employee-{index}",
            roles=["sales"],
            enabled=True,
            calendar_integration_id=f"calendar-{index}",
            timezone="America/Los_Angeles",
        )
        for index in (1, 2, 3)
    ]
    scheduling = SimpleNamespace(
        enabled=True,
        roles=[role],
        bookable_people=people,
        slot_duration_minutes=15,
        minimum_notice_minutes=0,
    )
    version = SimpleNamespace(config={})
    contact = SimpleNamespace(timezone="Asia/Kolkata")
    calendars = [
        None,
        SimpleNamespace(id="calendar-2", status="connected", timezone="UTC"),
        SimpleNamespace(id="calendar-3", status="connected", timezone="UTC"),
    ]
    session = SimpleNamespace(get=AsyncMock(side_effect=[version, contact, *calendars]))
    monkeypatch.setattr(
        calendar_endpoint.AgentConfig,
        "model_validate",
        lambda _config: SimpleNamespace(callback_scheduling=scheduling),
    )
    calls = []

    async def freebusy(_session, integration, _operation, **kwargs):
        calls.append((integration.id, kwargs["timezone"], kwargs["start"].tzinfo))
        return []

    monkeypatch.setattr(calendar_endpoint, "calendar_call", freebusy)
    result = await calendar_endpoint.availability(
        calendar_endpoint.AvailabilityRequest(
            agent_version_id="agent-version",
            contact_id="contact-1",
            timeframe="tomorrow morning",
            role="sales",
        ),
        session=session,
        _=None,
    )

    assert result["status"] == "partial_availability"
    assert len(result["slots"]) == 3
    assert [call[0] for call in calls] == ["calendar-2", "calendar-3"]
    assert [call[1] for call in calls] == ["Asia/Kolkata", "Asia/Kolkata"]
    assert calls[0][2].key == "Asia/Kolkata"
    assert calls[1][2].key == "Asia/Kolkata"
    from voice_api.services.calendar_service import verify_slot

    assignment = verify_slot(result["slots"][0]["slot_id"])
    assert assignment["person"] == "employee-2"
    assert assignment["timezone"] == "Asia/Kolkata"


@pytest.mark.asyncio
async def test_availability_requires_contact_timezone_before_calendar_queries(monkeypatch):
    version = SimpleNamespace(config={})
    contact = SimpleNamespace(timezone=None)
    session = SimpleNamespace(get=AsyncMock(side_effect=[version, contact]))
    result = await calendar_endpoint.availability(
        calendar_endpoint.AvailabilityRequest(
            agent_version_id="agent-version",
            contact_id="contact-1",
            timeframe="tomorrow morning",
            role="sales",
        ),
        session=session,
        _=None,
    )
    assert result["status"] == "timezone_required"
    assert session.get.await_count == 2


@pytest.mark.asyncio
async def test_availability_with_only_disconnected_calendars_is_not_no_availability(monkeypatch):
    role = SimpleNamespace(key="sales", enabled=True)
    person = SimpleNamespace(
        key="employee",
        roles=["sales"],
        enabled=True,
        calendar_integration_id="calendar-integration",
    )
    scheduling = SimpleNamespace(
        enabled=True,
        roles=[role],
        bookable_people=[person],
        slot_duration_minutes=15,
        minimum_notice_minutes=0,
    )
    version = SimpleNamespace(config={})
    contact = SimpleNamespace(timezone="Asia/Kolkata")
    disconnected = SimpleNamespace(status="disconnected")
    session = SimpleNamespace(get=AsyncMock(side_effect=[version, contact, disconnected]))
    monkeypatch.setattr(
        calendar_endpoint.AgentConfig,
        "model_validate",
        lambda _config: SimpleNamespace(callback_scheduling=scheduling),
    )

    result = await calendar_endpoint.availability(
        calendar_endpoint.AvailabilityRequest(
            agent_version_id="agent-version",
            contact_id="contact-1",
            timeframe="tomorrow morning",
            role="sales",
        ),
        session=session,
        _=None,
    )

    assert result["status"] == "calendar_unavailable"


@pytest.mark.asyncio
async def test_booking_rejects_slot_when_contact_timezone_has_changed(monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setattr(
        calendar_endpoint,
        "verify_slot",
        lambda _slot: {
            "agent_version_id": "agent-version",
            "contact_id": "contact-1",
            "integration": "calendar-integration",
            "timezone": "Asia/Kolkata",
        },
    )
    integration = SimpleNamespace(status="connected")
    contact = SimpleNamespace(timezone="Asia/Dubai")
    session = SimpleNamespace(get=AsyncMock(side_effect=[integration, contact]))

    with pytest.raises(HTTPException) as error:
        await calendar_endpoint.book(
            calendar_endpoint.BookRequest(
                agent_version_id="agent-version",
                contact_id="contact-1",
                slot_id="signed-slot",
                reason="Caller request",
            ),
            session=session,
            _=None,
        )

    assert error.value.status_code == 409
    assert "timezone changed" in error.value.detail


@pytest.mark.asyncio
async def test_booking_uses_signed_person_calendar_and_persists_confirmed_callback(monkeypatch):
    slot = {
        "agent_version_id": "agent-version",
        "contact_id": "contact-1",
        "integration": "calendar-integration",
        "timezone": "Asia/Kolkata",
        "start": "2026-10-01T10:00:00+05:30",
        "end": "2026-10-01T10:15:00+05:30",
        "window_start": "2026-10-01T09:00:00+05:30",
        "window_end": "2026-10-01T12:00:00+05:30",
        "timeframe": "tomorrow morning",
        "role": "sales",
        "person": "employee-2",
    }
    monkeypatch.setattr(calendar_endpoint, "verify_slot", lambda _slot: slot)
    integration = SimpleNamespace(id="calendar-integration", status="connected")
    contact = SimpleNamespace(timezone="Asia/Kolkata", name="Caller", phone_number="+15551234567")
    callbacks = []
    session = SimpleNamespace(
        get=AsyncMock(side_effect=[integration, contact]),
        add=callbacks.append,
        flush=AsyncMock(),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )
    calls = []

    async def calendar_operation(_session, calendar, operation, **kwargs):
        calls.append((calendar.id, operation, kwargs))
        return [] if operation == "freebusy" else {"id": "event-42"}

    monkeypatch.setattr(calendar_endpoint, "calendar_call", calendar_operation)
    result = await calendar_endpoint.book(
        calendar_endpoint.BookRequest(
            agent_version_id="agent-version",
            contact_id="contact-1",
            slot_id="signed-slot",
            reason="Caller requested a callback",
        ),
        session=session,
        _=None,
    )

    assert result["status"] == "confirmed"
    assert result["duration_minutes"] == 15
    assert calls[0][0:2] == ("calendar-integration", "freebusy")
    assert calls[1][0:2] == ("calendar-integration", "insert")
    assert len(callbacks) == 1
    assert callbacks[0].role_key == "sales"
    assert callbacks[0].bookable_person_key == "employee-2"
    assert callbacks[0].calendar_event_id == "event-42"


@pytest.mark.asyncio
async def test_availability_with_no_contact_id_requires_timezone():
    session = SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(config={})))
    result = await calendar_endpoint.availability(
        calendar_endpoint.AvailabilityRequest(
            agent_version_id="agent-version",
            timeframe="tomorrow morning",
            role="sales",
        ),
        session=session,
        _=None,
    )
    assert result["status"] == "timezone_required"
    assert session.get.await_count == 1


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
