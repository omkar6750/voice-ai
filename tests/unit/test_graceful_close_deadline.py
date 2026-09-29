"""Bound goodbye draining independently of call duration and wall-clock jumps."""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import voice_runtime.execution.termination as termination_module
from voice_runtime.execution.native import NativePipelineHost
from voice_runtime.execution.termination import CallTermination


def test_monotonic_deadline_is_not_reset_by_repeated_end_requests(monkeypatch):
    clock = [10.0]
    monkeypatch.setattr(termination_module.time, "monotonic", lambda: clock[0])
    call = CallTermination()
    call.request("agent_hangup", graceful=True)
    clock[0] = 24.0
    call.request("agent_hangup", graceful=True)
    assert not call.graceful_deadline_expired(15)
    clock[0] = 25.0
    assert call.graceful_deadline_expired(15)
    call.request("drain_timeout")
    assert call.summary.cause == "drain_timeout"
    assert call.summary.mode == "immediate"
    call.pipeline_finished()
    assert call.summary.execution_status == "failed"


def test_completed_or_immediate_call_does_not_have_a_graceful_deadline(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(termination_module.time, "monotonic", lambda: clock[0])
    call = CallTermination()
    assert not call.graceful_deadline_expired(15)
    call.request("agent_hangup", graceful=True)
    call.pipeline_finished()
    clock[0] = 100.0
    assert not call.graceful_deadline_expired(15)
    other = CallTermination()
    other.request("caller_hangup")
    clock[0] = 200.0
    assert not other.graceful_deadline_expired(15)


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
def test_host_rejects_unbounded_or_non_positive_timeout(timeout):
    with pytest.raises(ValueError, match="finite and positive"):
        NativePipelineHost(
            "run", Path("unused"), SimpleNamespace(), graceful_close_timeout_secs=timeout
        )


async def test_stalled_native_goodbye_cancels_and_reports_timeout(monkeypatch):
    value = NativePipelineHost("run", Path("unused"), SimpleNamespace())
    value._snapshot = {"flow": {"initial_node": "closing"}}
    value._node = Mock(return_value={})
    value.flow = SimpleNamespace(initialize=AsyncMock(), current_node="closing")
    value.tracker = Mock()
    stopped = asyncio.Event()
    value.runner_task = asyncio.create_task(stopped.wait())
    value.worker = SimpleNamespace(
        queue_frame=AsyncMock(), cancel=AsyncMock(side_effect=stopped.set)
    )
    value.termination.request("agent_hangup", graceful=True)
    monkeypatch.setattr(value.termination, "graceful_deadline_expired", lambda timeout: True)
    try:
        with pytest.raises(TimeoutError, match="exceeded its deadline"):
            await value.converse()
        assert value.termination.summary.cause == "drain_timeout"
        assert value.termination.summary.requested_cause == "agent_hangup"
        value.worker.cancel.assert_awaited_once()
        assert value.tracker.diagnostic.call_args.kwargs["code"] == "graceful_close_timeout"
        await value.close()
        value.tracker.end_exchange.assert_called_once_with("failed")
    finally:
        stopped.set()
        await value.runner_task
