"""Terminal cleanup persists independently of transcript/evidence delivery."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from voice_api.api.v1.endpoints import runtime
from voice_shared.contracts import RuntimeSync


@pytest.mark.parametrize("cleanup", ["confirmed", "uncertain"])
@pytest.mark.parametrize(
    "cause", ["evidence_failure", "duration_limit", "pipeline_failure", "cancelled"]
)
async def test_terminal_sync_updates_run_call_callback_and_lease(monkeypatch, cleanup, cause):
    identity = {key: uuid4() for key in ("run_id", "generation", "boot_id")}
    run = SimpleNamespace(
        id=str(identity["run_id"]),
        status="uncertain",
        error="Runtime lease expired; execution and transport release are unconfirmed",
        ended_at=None,
        final_state={},
        channel="phone",
    )
    assignment = SimpleNamespace(
        state="uncertain", lease_expires_at=datetime.now(UTC) - timedelta(minutes=1)
    )
    call = SimpleNamespace(id=str(uuid4()), provider="sim7600", status="uncertain", ended_at=None)
    callback = SimpleNamespace(status="uncertain", completed_at=None)
    session = SimpleNamespace(
        scalar=AsyncMock(side_effect=[call, None, callback]),
        execute=AsyncMock(),
        scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: [])),
        commit=AsyncMock(),
    )
    monkeypatch.setattr(runtime, "authorize", AsyncMock(return_value=(assignment, run)))
    body = RuntimeSync(
        **identity,
        grant="test-grant",
        lifecycle={
            "termination": {"cause": cause, "cleanup_status": cleanup},
            "evidence_incomplete": True,
        },
    )
    reply = await runtime.sync(body, session)
    assert (
        run.status
        == call.status
        == callback.status
        == (
            ("cancelled" if cause == "cancelled" else "failed")
            if cleanup == "confirmed"
            else "uncertain"
        )
    )
    assert assignment.state == ("ended" if cleanup == "confirmed" else "uncertain")
    assert (run.ended_at is not None) == (cleanup == "confirmed")
    assert run.final_state["termination"]["cause"] == cause
    assert run.final_state["evidence_incomplete"] is True
    assert "Runtime lease expired" not in (run.error or "")
    assert reply["accepted"] == 0 and not reply["stop"]
    session.commit.assert_awaited_once()
