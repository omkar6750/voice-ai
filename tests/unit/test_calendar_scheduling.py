from datetime import UTC, datetime

import pytest
from voice_api.services.calendar_service import (
    BusyPeriod,
    SchedulingError,
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
