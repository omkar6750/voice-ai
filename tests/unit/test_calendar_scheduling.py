from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
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
    sign_callback_slot,
    verify_callback_slot,
)


def test_compact_callback_slot_round_trip_is_bound_to_run(monkeypatch):
    monkeypatch.setattr(
        calendar_service,
        "get_settings",
        lambda: SimpleNamespace(callback_slot_signing_key="test-key"),
    )
    start = datetime(2026, 10, 2, 11, 30, tzinfo=UTC)
    expires_at = datetime(2026, 10, 1, 10, 24, tzinfo=UTC)

    token = sign_callback_slot(
        run_id="c530384e-c237-4f7b-82bb-4bebad84827d",
        calendar_integration_id="6db92f26-467b-4237-bceb-cb6dd980391d",
        start=start,
        duration_minutes=30,
        expires_at=expires_at,
        role_index=2,
    )

    assert len(token) == 58
    claims = verify_callback_slot(
        token,
        run_id="c530384e-c237-4f7b-82bb-4bebad84827d",
        reference=datetime(2026, 10, 1, 10, 20, tzinfo=UTC),
    )
    assert claims == {
        "integration": "6db92f26-467b-4237-bceb-cb6dd980391d",
        "start": start,
        "end": start + timedelta(minutes=30),
        "expires_at": expires_at,
        "role_index": 2,
    }


def test_compact_callback_slot_rejects_another_run(monkeypatch):
    monkeypatch.setattr(
        calendar_service,
        "get_settings",
        lambda: SimpleNamespace(callback_slot_signing_key="test-key"),
    )
    token = sign_callback_slot(
        run_id="c530384e-c237-4f7b-82bb-4bebad84827d",
        calendar_integration_id="6db92f26-467b-4237-bceb-cb6dd980391d",
        start=datetime(2026, 10, 2, 11, 30, tzinfo=UTC),
        duration_minutes=30,
        expires_at=datetime(2026, 10, 1, 10, 24, tzinfo=UTC),
        role_index=0,
    )

    with pytest.raises(SchedulingError, match="Invalid callback slot"):
        verify_callback_slot(
            token,
            run_id="b56de66c-9046-4699-9f9a-8a3b4088d84f",
            reference=datetime(2026, 10, 1, 10, 20, tzinfo=UTC),
        )


def test_compact_callback_slot_rejects_tampering(monkeypatch):
    monkeypatch.setattr(
        calendar_service,
        "get_settings",
        lambda: SimpleNamespace(callback_slot_signing_key="test-key"),
    )
    token = sign_callback_slot(
        run_id="c530384e-c237-4f7b-82bb-4bebad84827d",
        calendar_integration_id="6db92f26-467b-4237-bceb-cb6dd980391d",
        start=datetime(2026, 10, 2, 11, 30, tzinfo=UTC),
        duration_minutes=30,
        expires_at=datetime(2026, 10, 1, 10, 24, tzinfo=UTC),
        role_index=0,
    )
    replacement = "A" if token[-1] != "A" else "B"

    with pytest.raises(SchedulingError, match="Invalid callback slot"):
        verify_callback_slot(
            token[:-1] + replacement,
            run_id="c530384e-c237-4f7b-82bb-4bebad84827d",
            reference=datetime(2026, 10, 1, 10, 20, tzinfo=UTC),
        )


def test_compact_callback_slot_rejects_expired_token(monkeypatch):
    monkeypatch.setattr(
        calendar_service,
        "get_settings",
        lambda: SimpleNamespace(callback_slot_signing_key="test-key"),
    )
    token = sign_callback_slot(
        run_id="c530384e-c237-4f7b-82bb-4bebad84827d",
        calendar_integration_id="6db92f26-467b-4237-bceb-cb6dd980391d",
        start=datetime(2026, 10, 2, 11, 30, tzinfo=UTC),
        duration_minutes=30,
        expires_at=datetime(2026, 10, 1, 10, 24, tzinfo=UTC),
        role_index=0,
    )

    with pytest.raises(SchedulingError, match="expired"):
        verify_callback_slot(
            token,
            run_id="c530384e-c237-4f7b-82bb-4bebad84827d",
            reference=datetime(2026, 10, 1, 10, 25, tzinfo=UTC),
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


def test_callback_confirmation_uses_tts_safe_local_time_format():
    value = datetime(2026, 9, 26, 5, 0, tzinfo=UTC)
    assert format_local_callback_time(value, "Asia/Kolkata") == (
        "Saturday at ten thirty in the morning"
    )


def test_callback_confirmation_speaks_whole_hours_without_timezone_identifiers():
    value = datetime(2026, 10, 2, 11, 30, tzinfo=UTC)
    assert format_local_callback_time(value, "Asia/Kolkata") == (
        "Friday at five in the evening"
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
    monkeypatch.setattr(
        "voice_api.services.calendar_service.build", lambda *_args, **_kwargs: Service()
    )
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
    run = SimpleNamespace(
        id="c530384e-c237-4f7b-82bb-4bebad84827d",
        agent_version_id="agent-version",
        contact_id="contact-1",
    )
    version = SimpleNamespace(config={})
    contact = SimpleNamespace(timezone="Asia/Kolkata")
    integration = SimpleNamespace(status="connected", timezone="UTC")
    session = SimpleNamespace(get=AsyncMock(side_effect=[run, version, contact, integration]))

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
            run_id=run.id,
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
    calendar_ids = [
        "6db92f26-467b-4237-bceb-cb6dd980391d",
        "2863afc7-956c-4822-84b0-33f465e524cc",
        "0b4e927f-8d55-4cb2-a559-1b113a657bc3",
    ]
    people = [
        SimpleNamespace(
            key=f"employee-{index}",
            roles=["sales"],
            enabled=True,
            calendar_integration_id=calendar_ids[index - 1],
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
    run = SimpleNamespace(
        id="c530384e-c237-4f7b-82bb-4bebad84827d",
        agent_version_id="agent-version",
        contact_id="contact-1",
    )
    version = SimpleNamespace(config={})
    contact = SimpleNamespace(timezone="Asia/Kolkata")
    calendars = [
        None,
        SimpleNamespace(id=calendar_ids[1], status="connected", timezone="UTC"),
        SimpleNamespace(id=calendar_ids[2], status="connected", timezone="UTC"),
    ]
    session = SimpleNamespace(get=AsyncMock(side_effect=[run, version, contact, *calendars]))
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
            run_id=run.id,
            timeframe="tomorrow morning",
            role="sales",
        ),
        session=session,
        _=None,
    )

    assert result["status"] == "partial_availability"
    assert len(result["slots"]) == 3
    assert all("Asia/" not in slot["display"] for slot in result["slots"])
    assert all(not any(char.isdigit() for char in slot["display"]) for slot in result["slots"])
    assert "exactly as written" in result["message"]
    assert "Never read or alter a slot ID" in result["message"]
    assert [call[0] for call in calls] == calendar_ids[1:]
    assert [call[1] for call in calls] == ["Asia/Kolkata", "Asia/Kolkata"]
    assert calls[0][2].key == "Asia/Kolkata"
    assert calls[1][2].key == "Asia/Kolkata"
    assignment = verify_callback_slot(result["slots"][0]["slot_id"], run_id=run.id)
    assert assignment["integration"] == calendar_ids[1]
    assert assignment["role_index"] == 0
    assert len(result["slots"][0]["slot_id"]) == 58


@pytest.mark.asyncio
async def test_availability_requires_contact_timezone_before_calendar_queries(monkeypatch):
    run = SimpleNamespace(
        id="c530384e-c237-4f7b-82bb-4bebad84827d",
        agent_version_id="agent-version",
        contact_id="contact-1",
    )
    version = SimpleNamespace(config={})
    contact = SimpleNamespace(timezone=None)
    session = SimpleNamespace(get=AsyncMock(side_effect=[run, version, contact]))
    result = await calendar_endpoint.availability(
        calendar_endpoint.AvailabilityRequest(
            run_id=run.id,
            timeframe="tomorrow morning",
            role="sales",
        ),
        session=session,
        _=None,
    )
    assert result["status"] == "timezone_required"
    assert session.get.await_count == 3


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
    run = SimpleNamespace(
        id="c530384e-c237-4f7b-82bb-4bebad84827d",
        agent_version_id="agent-version",
        contact_id="contact-1",
    )
    version = SimpleNamespace(config={})
    contact = SimpleNamespace(timezone="Asia/Kolkata")
    disconnected = SimpleNamespace(status="disconnected")
    session = SimpleNamespace(get=AsyncMock(side_effect=[run, version, contact, disconnected]))
    monkeypatch.setattr(
        calendar_endpoint.AgentConfig,
        "model_validate",
        lambda _config: SimpleNamespace(callback_scheduling=scheduling),
    )

    result = await calendar_endpoint.availability(
        calendar_endpoint.AvailabilityRequest(
            run_id=run.id,
            timeframe="tomorrow morning",
            role="sales",
        ),
        session=session,
        _=None,
    )

    assert result["status"] == "calendar_unavailable"


@pytest.mark.asyncio
async def test_booking_rejects_slot_when_callback_configuration_has_changed(monkeypatch):
    run = SimpleNamespace(
        id="c530384e-c237-4f7b-82bb-4bebad84827d",
        agent_version_id="agent-version",
        contact_id="contact-1",
    )
    version = SimpleNamespace(config={})
    contact = SimpleNamespace(timezone="Asia/Dubai")
    monkeypatch.setattr(
        calendar_endpoint,
        "verify_callback_slot",
        lambda _slot, *, run_id: {
            "integration": "calendar-integration",
            "start": datetime(2026, 10, 1, 4, 30, tzinfo=UTC),
            "end": datetime(2026, 10, 1, 4, 45, tzinfo=UTC),
            "role_index": 1,
        },
    )
    monkeypatch.setattr(
        calendar_endpoint.AgentConfig,
        "model_validate",
        lambda _config: SimpleNamespace(
            callback_scheduling=SimpleNamespace(roles=[], bookable_people=[])
        ),
    )
    session = SimpleNamespace(get=AsyncMock(side_effect=[run, version, contact]))

    with pytest.raises(HTTPException) as error:
        await calendar_endpoint.book(
            calendar_endpoint.BookRequest(
                run_id=run.id,
                slot_id="signed-slot",
                reason="Caller request",
            ),
            session=session,
            _=None,
        )

    assert error.value.status_code == 409
    assert "configuration changed" in error.value.detail


@pytest.mark.asyncio
async def test_booking_uses_signed_person_calendar_and_persists_confirmed_callback(monkeypatch):
    run = SimpleNamespace(
        id="c530384e-c237-4f7b-82bb-4bebad84827d",
        agent_version_id="agent-version",
        contact_id="contact-1",
    )
    slot = {
        "integration": "calendar-integration",
        "start": datetime(2026, 10, 1, 4, 30, tzinfo=UTC),
        "end": datetime(2026, 10, 1, 4, 45, tzinfo=UTC),
        "role_index": 0,
    }
    role = SimpleNamespace(key="sales", enabled=True)
    person = SimpleNamespace(
        key="employee-2",
        roles=["sales"],
        enabled=True,
        calendar_integration_id="calendar-integration",
    )
    scheduling = SimpleNamespace(roles=[role], bookable_people=[person])
    version = SimpleNamespace(config={})
    monkeypatch.setattr(calendar_endpoint, "verify_callback_slot", lambda _slot, *, run_id: slot)
    monkeypatch.setattr(
        calendar_endpoint.AgentConfig,
        "model_validate",
        lambda _config: SimpleNamespace(callback_scheduling=scheduling),
    )
    integration = SimpleNamespace(id="calendar-integration", status="connected")
    contact = SimpleNamespace(timezone="Asia/Kolkata", name="Caller", phone_number="+15551234567")
    callbacks = []
    session = SimpleNamespace(
        get=AsyncMock(side_effect=[run, version, contact, integration]),
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
            run_id=run.id,
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
    run = SimpleNamespace(
        id="c530384e-c237-4f7b-82bb-4bebad84827d",
        agent_version_id="agent-version",
        contact_id=None,
    )
    version = SimpleNamespace(config={})
    session = SimpleNamespace(get=AsyncMock(side_effect=[run, version]))
    result = await calendar_endpoint.availability(
        calendar_endpoint.AvailabilityRequest(
            run_id=run.id,
            timeframe="tomorrow morning",
            role="sales",
        ),
        session=session,
        _=None,
    )
    assert result["status"] == "timezone_required"
    assert session.get.await_count == 2


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
    monkeypatch.setattr(
        "voice_api.services.calendar_service.build", lambda *_args, **_kwargs: Service()
    )
    kwargs = {"event": {"summary": "Test"}} if operation == "insert" else {"event_id": "event-123"}
    await calendar_call(None, integration, operation, **kwargs)
    assert calls[0][1] == integration.calendar_id


@pytest.mark.asyncio
async def test_calendar_test_availability_returns_five_signed_org_slots(monkeypatch):
    integration = SimpleNamespace(
        id="calendar-integration",
        status="connected",
        timezone="Asia/Kolkata",
    )
    session = SimpleNamespace(
        get=AsyncMock(return_value=integration),
        sync_session=object(),
    )
    start = datetime(2026, 10, 2, 10, 0, tzinfo=UTC)
    generated = [
        (start + timedelta(minutes=index * 15), start + timedelta(minutes=(index + 1) * 15))
        for index in range(5)
    ]

    async def freebusy(*_args, **_kwargs):
        return []

    monkeypatch.setattr(calendar_endpoint, "calendar_call", freebusy)
    monkeypatch.setattr(calendar_endpoint, "generate_slots", lambda *_args, **_kwargs: generated)
    monkeypatch.setattr(calendar_endpoint, "required_organization", lambda _session: "org-1")
    monkeypatch.setattr(
        calendar_endpoint, "sign_slot", lambda payload: f"signed:{payload['start']}"
    )

    result = await calendar_endpoint.test_calendar_availability(
        "calendar-integration",
        calendar_endpoint.CalendarTestAvailabilityRequest(limit=5),
        session=session,
        _=None,
    )

    assert result["timezone"] == "Asia/Kolkata"
    assert len(result["slots"]) == 5
    assert result["slots"][0]["slot_id"].startswith("signed:")


@pytest.mark.asyncio
async def test_calendar_test_availability_reports_missing_signing_configuration(monkeypatch):
    integration = SimpleNamespace(
        id="calendar-integration",
        status="connected",
        timezone="UTC",
    )
    session = SimpleNamespace(
        get=AsyncMock(return_value=integration),
        sync_session=object(),
    )
    start = datetime(2026, 10, 2, 10, 0, tzinfo=UTC)

    async def freebusy(*_args, **_kwargs):
        return []

    def missing_signing_key(_payload):
        raise SchedulingError("Callback slot signing is not configured")

    monkeypatch.setattr(calendar_endpoint, "calendar_call", freebusy)
    monkeypatch.setattr(
        calendar_endpoint,
        "generate_slots",
        lambda *_args, **_kwargs: [(start, start + timedelta(minutes=15))],
    )
    monkeypatch.setattr(calendar_endpoint, "required_organization", lambda _session: "org-1")
    monkeypatch.setattr(calendar_endpoint, "sign_slot", missing_signing_key)

    with pytest.raises(HTTPException) as error:
        await calendar_endpoint.test_calendar_availability(
            "calendar-integration",
            calendar_endpoint.CalendarTestAvailabilityRequest(limit=5),
            session=session,
            _=None,
        )

    assert error.value.status_code == 503
    assert error.value.detail == "Calendar slot signing is not configured"


@pytest.mark.asyncio
async def test_calendar_test_booking_rechecks_and_inserts_test_event(monkeypatch):
    slot = {
        "purpose": "calendar_integration_test",
        "organization_id": "org-1",
        "integration": "calendar-integration",
        "timezone": "UTC",
        "start": "2026-10-02T10:00:00+00:00",
        "end": "2026-10-02T10:15:00+00:00",
    }
    integration = SimpleNamespace(
        id="calendar-integration",
        status="connected",
        timezone="UTC",
    )
    session = SimpleNamespace(
        get=AsyncMock(return_value=integration),
        commit=AsyncMock(),
        sync_session=object(),
    )
    calls = []

    async def calendar_operation(_session, _integration, operation, **kwargs):
        calls.append((operation, kwargs))
        return [] if operation == "freebusy" else {"id": "event-test-1"}

    monkeypatch.setattr(calendar_endpoint, "verify_slot", lambda _value: slot)
    monkeypatch.setattr(calendar_endpoint, "required_organization", lambda _session: "org-1")
    monkeypatch.setattr(calendar_endpoint, "calendar_call", calendar_operation)

    result = await calendar_endpoint.test_calendar_booking(
        "calendar-integration",
        calendar_endpoint.CalendarTestBookingRequest(
            slot_id="signed-slot",
            summary="Calendar test",
            description="Created before a demo call",
        ),
        session=session,
        _=None,
    )

    assert result["status"] == "confirmed"
    assert result["event_id"] == "event-test-1"
    assert [operation for operation, _kwargs in calls] == ["freebusy", "insert"]
    assert calls[1][1]["event"]["extendedProperties"]["private"] == {
        "voice_ai_integration_test": "true"
    }
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_calendar_test_booking_rejects_slot_from_another_integration(monkeypatch):
    monkeypatch.setattr(
        calendar_endpoint,
        "verify_slot",
        lambda _value: {
            "purpose": "calendar_integration_test",
            "organization_id": "org-1",
            "integration": "another-calendar",
        },
    )
    monkeypatch.setattr(calendar_endpoint, "required_organization", lambda _session: "org-1")
    session = SimpleNamespace(sync_session=object(), get=AsyncMock())

    with pytest.raises(HTTPException) as error:
        await calendar_endpoint.test_calendar_booking(
            "calendar-integration",
            calendar_endpoint.CalendarTestBookingRequest(
                slot_id="signed-slot",
                summary="Calendar test",
            ),
            session=session,
            _=None,
        )

    assert error.value.status_code == 409
    assert session.get.await_count == 0
