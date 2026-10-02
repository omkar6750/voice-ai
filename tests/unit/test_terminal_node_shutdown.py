"""Terminal nodes use an ordered Pipecat action; entering one is not completion."""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from pipecat.flows.actions import ActionManager, FunctionActionFrame
from pipecat.frames.frames import EndFrame
from voice_runtime.execution.native import NativePipelineHost


def host():
    value = NativePipelineHost("run", Path("unused"), SimpleNamespace())
    value.tracker = Mock()
    value._snapshot = {
        "flow": {
            "initial_node": "closing",
            "nodes": [
                {
                    "id": "closing",
                    "prompt": "Goodbye",
                    "terminal": True,
                    "tool_bindings": [],
                    "transitions": [],
                    "respond_immediately": True,
                }
            ],
        },
        "_resolved": {"tools": {}},
    }
    value._nodes = {
        "closing": {
            "prompt": "Goodbye",
            "terminal": True,
            "tool_bindings": [],
            "transitions": [],
            "respond_immediately": True,
        }
    }
    value.worker = SimpleNamespace(queue_frame=AsyncMock())
    return value


def test_only_terminal_nodes_receive_ordered_internal_close_action():
    value = host()
    terminal = value._node("closing")
    assert terminal["post_actions"][0]["type"] == "function"
    assert not value.termination.closing
    value._nodes["closing"]["terminal"] = False
    assert "post_actions" not in value._node("closing")


async def test_pipecat_function_action_is_queued_before_close_is_requested():
    value = host()
    callbacks = {}

    def event_handler(name):
        def register(callback):
            callbacks[name] = callback
            return callback

        return register

    worker = SimpleNamespace(
        queue_frame=AsyncMock(), set_reached_downstream_filter=Mock(), event_handler=event_handler
    )
    value.worker = worker
    manager = SimpleNamespace(current_node="closing")
    actions = ActionManager(worker, manager)
    task = asyncio.create_task(actions.execute_actions(value._node("closing")["post_actions"]))
    await asyncio.sleep(0)
    frame = worker.queue_frame.await_args.args[0]
    assert isinstance(frame, FunctionActionFrame)
    assert not value.termination.closing
    # The real transport delivers this frame after preceding audio, then Flows
    # invokes the handler. Exercise the installed ActionManager callback itself.
    await callbacks["on_frame_reached_downstream"](worker, frame)
    await task
    assert value.termination.summary.cause == "terminal_completed"
    assert value.termination.summary.terminal_node == "closing"
    assert isinstance(worker.queue_frame.await_args.args[0], EndFrame)
    assert value.termination.summary.execution_status == "failed"  # not finished yet
    value.termination.pipeline_finished()
    assert value.termination.summary.execution_status == "completed"
    # Local action completion does not prove carrier drain or transport release.
    assert value.termination.summary.cleanup_status == "unknown"
    assert value.termination.summary.playback_status == "unknown"


@pytest.mark.parametrize("cause", ["caller_hangup", "disconnect_unknown", "pipeline_failure"])
async def test_terminal_action_cannot_overwrite_prior_disconnect_or_error(cause):
    value = host()
    value.termination.request(cause)
    await value._terminal_response_finished(
        {"node": "closing"}, SimpleNamespace(current_node="closing")
    )
    assert value.termination.summary.cause == cause
    value.worker.queue_frame.assert_not_awaited()


async def test_stale_terminal_action_does_not_close_a_different_node():
    value = host()
    await value._terminal_response_finished(
        {"node": "closing"}, SimpleNamespace(current_node="other")
    )
    assert not value.termination.closing
    value.worker.queue_frame.assert_not_awaited()


async def test_duplicate_terminal_completion_queues_end_once():
    value = host()
    manager = SimpleNamespace(current_node="closing")
    await value._terminal_response_finished({"node": "closing"}, manager)
    await value._terminal_response_finished({"node": "closing"}, manager)
    value.worker.queue_frame.assert_awaited_once()
    value.tracker.diagnostic.assert_called_once()


async def test_terminal_queue_failure_cannot_become_success():
    value = host()
    value.worker.queue_frame.side_effect = RuntimeError("worker unavailable")
    with pytest.raises(RuntimeError, match="worker unavailable"):
        await value._terminal_response_finished(
            {"node": "closing"}, SimpleNamespace(current_node="closing")
        )
    value.termination.pipeline_finished()
    assert value.termination.summary.cause == "pipeline_failure"
    assert value.termination.summary.execution_status == "failed"
    assert value.errors == ["Terminal shutdown could not be queued"]
    assert value.tracker.diagnostic.call_args.kwargs["code"] == "terminal_shutdown_failed"
