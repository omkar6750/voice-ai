"""Native cleanup cannot fabricate successful evidence from a shutdown intent."""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from voice_runtime.execution.native import NativePipelineHost


def host():
    value = NativePipelineHost("run-1", Path("unused"), SimpleNamespace())
    value.worker = SimpleNamespace(queue_frame=AsyncMock(), cancel=AsyncMock())
    value.tracker = Mock()
    value.observer = Mock()
    value.capture = Mock()
    value._snapshot = {"flow": {"initial_node": "start"}}
    value.flow = SimpleNamespace(initialize=AsyncMock(), current_node="start")
    value._node = Mock(return_value={"name": "start"})
    return value


async def test_pipeline_failure_after_agent_end_intent_is_not_suppressed():
    value = host()
    await value._handler("end_call")({}, None)
    await value._pipeline_failed(SimpleNamespace(error="TTS failed"))
    with pytest.raises(RuntimeError, match="Pipeline failed"):
        await value.converse()
    await value.close()
    assert value.termination.summary.cause == "pipeline_failure"
    value.tracker.end_visit.assert_called_once_with("failed")
    value.tracker.end_exchange.assert_called_once_with("failed")


async def test_cleanup_without_completion_intent_is_interrupted_not_completed():
    value = host()
    await value.close()
    assert value.termination.summary.cause == "cancelled"
    value.tracker.end_exchange.assert_called_once_with("interrupted")


async def test_successful_agent_close_returns_explicit_termination_facts():
    value = host()
    await value._handler("end_call")({}, None)
    result = await value.converse()
    assert result["flow_node"] == "start"
    assert result["termination"]["cause"] == "agent_hangup"
    assert result["termination"]["pipeline_finished_at_ns"] is not None
    # Pipeline completion is not proof that the carrier hung up.
    assert result["termination"]["cleanup_status"] == "unknown"
    await value.close()
    value.tracker.end_exchange.assert_called_once_with("completed")


async def test_unexplained_pipeline_finish_is_not_a_successful_call():
    value = host()
    result = await value.converse()
    assert result["termination"]["cause"] == "unknown"
    await value.close()
    assert value.termination.summary.cause == "unknown"
    value.tracker.end_exchange.assert_called_once_with("failed")


async def test_liveness_loss_is_not_assumed_caller_hangup():
    value = host()

    async def inactive():
        return False

    await value._record_call_termination(inactive)
    assert value.termination.summary.cause == "disconnect_unknown"
    await value.close()
    assert value.termination.summary.cause == "disconnect_unknown"
    value.tracker.end_exchange.assert_called_once_with("interrupted")


async def test_idle_timeout_cause_survives_cleanup_cancellation():
    value = host()
    await value._handle_user_idle()
    await value._handle_user_idle()
    await value._end_task
    await value.close()
    assert value.termination.summary.cause == "caller_idle_timeout"
    value.tracker.end_exchange.assert_called_once_with("failed")


async def test_runner_failure_during_cleanup_is_failed_evidence():
    value = host()

    async def broken_runner():
        raise RuntimeError("runner failed")

    value.runner_task = asyncio.create_task(broken_runner())
    await asyncio.sleep(0)
    with pytest.raises(RuntimeError, match="runner failed"):
        await value.close()
    value.tracker.end_exchange.assert_called_once_with("failed")
    value.observer.close.assert_called_once()
    value.capture.close.assert_called_once()
