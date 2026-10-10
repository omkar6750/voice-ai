"""Operator stop preserves ownership until runtime cleanup is confirmed."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from voice_api.api.v1.endpoints.runs import stop_run
from voice_api.models import Run
from voice_api.services import runtime_dispatch


def session_for(status="running", assignment=None):
    run = SimpleNamespace(id="run", channel="phone", status=status, final_state={}, ended_at=None)
    call = SimpleNamespace(status="queued", ended_at=None)
    session = SimpleNamespace(
        get=AsyncMock(
            side_effect=lambda model, *args, **kwargs: run if model is Run else assignment
        ),
        scalar=AsyncMock(return_value=call),
        commit=AsyncMock(),
    )
    return session, run, call


async def test_queued_stop_cancels_before_dispatch():
    session, run, call = session_for("queued")
    reply = await stop_run("run", session)
    assert reply["status"] == run.status == call.status == "cancelled"
    assert run.ended_at == call.ended_at and run.ended_at is not None
    assert run.final_state["cancelled_before_dispatch"]


@pytest.mark.parametrize("boot_id", [None, "boot"])
async def test_live_stop_keeps_lease_and_fences_preparation(monkeypatch, boot_id):
    assignment = SimpleNamespace(state="active", boot_id=boot_id, run_id="run", generation="gen")
    session, run, _ = session_for(assignment=assignment)
    control = AsyncMock()
    monkeypatch.setattr(runtime_dispatch, "control", control)
    reply = await stop_run("run", session)
    assert reply["stop_requested"]
    assert run.status == "running" and run.ended_at is None
    assert assignment.state == "stopping"
    assert control.await_count == (1 if boot_id else 0)


async def test_terminal_stop_is_idempotent():
    session, _, _ = session_for("completed")
    assert not (await stop_run("run", session))["stop_requested"]
    session.commit.assert_not_awaited()


async def test_missing_owner_does_not_invent_transport_release():
    session, run, _ = session_for()
    with pytest.raises(HTTPException) as error:
        await stop_run("run", session)
    assert error.value.status_code == 409
    assert run.status == "running" and run.ended_at is None


async def test_out_of_scope_run_is_not_found():
    session, _, _ = session_for()
    session.get = AsyncMock(return_value=None)
    with pytest.raises(HTTPException) as error:
        await stop_run("run", session)
    assert error.value.status_code == 404
