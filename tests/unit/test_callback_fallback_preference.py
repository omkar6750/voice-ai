from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from voice_api.services.runtime_tools import BackendToolDispatch


@pytest.mark.asyncio
@pytest.mark.parametrize("preference", ["Sunday", "Sunday at 2 pm", "Sunday afternoon"])
async def test_fallback_preserves_preference_without_claiming_calendar_booking(
    monkeypatch, preference
):
    saved = []
    session = AsyncMock()
    session.add = saved.append
    session.__aenter__.return_value = session
    monkeypatch.setattr("voice_api.db.session.SessionFactory", lambda: session)
    monkeypatch.setattr("voice_api.db.tenant_scope.bind_run_organization", AsyncMock())
    from voice_api.services.calendar_service import resolve_timeframe

    monkeypatch.setattr(
        "voice_api.services.calendar_service.resolve_timeframe",
        lambda phrase, timezone: resolve_timeframe(
            phrase, timezone, reference=datetime(2026, 10, 8, tzinfo=UTC)
        ),
    )
    dispatch = BackendToolDispatch()
    dispatch.run_id = "run"
    dispatch._snapshot = {
        "contact_id": "contact",
        "agent_version_id": "agent",
        "contact_snapshot": {"timezone": "Asia/Kolkata"},
    }
    result = await dispatch._handler("schedule_callback")({"time": preference}, SimpleNamespace())
    assert result["status"] == "ok"
    assert result["requested_timeframe"] == preference
    assert result["booking_confirmed"] is False
    assert "scheduled_time" not in result
    assert "confirm a suitable time" in result["message"]
    assert saved[0].original_phrase == preference
    assert saved[0].scheduled_start is None
    assert saved[0].callback_mode == "human"
