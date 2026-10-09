import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from voice_runtime.execution.flow_manager import TracedFlowManager
from voice_runtime.execution.native_host import NativePipelineHost
from voice_runtime.execution.termination import CallTermination


@pytest.mark.asyncio
@pytest.mark.parametrize("failed", [False, True])
async def test_terminal_is_recorded_only_after_node_setup_succeeds(monkeypatch, failed):
    from pipecat.flows import FlowManager

    setup = AsyncMock(side_effect=RuntimeError("setup failed") if failed else None)
    monkeypatch.setattr(FlowManager, "_set_node", setup)
    termination = CallTermination()
    manager = object.__new__(TracedFlowManager)
    manager._current_node = "hot_followup"
    manager._classifier_runner = AsyncMock(return_value=None)
    manager._transition_tool_id = None
    manager.context_generation = 0
    manager._snapshot = {"flow": {"nodes": [{"id": "closing", "terminal": True}]}}
    manager.tracker = Mock()
    manager.termination = termination
    if failed:
        with pytest.raises(RuntimeError, match="setup failed"):
            await TracedFlowManager._set_node(manager, "closing", {})
        assert termination.summary.terminal_node is None
        manager.tracker.end_visit.assert_called_once_with("failed")
    else:
        await TracedFlowManager._set_node(manager, "closing", {})
        assert termination.summary.terminal_node == "closing"


async def test_terminal_entry_preserves_live_bound_action_and_finishes(monkeypatch):
    from pipecat.flows import FlowManager

    host = NativePipelineHost("test-run", Path("unused"), SimpleNamespace())
    # Reproduce the live task reachable through the bound terminal action.
    host.worker = SimpleNamespace(task=asyncio.current_task(), queue_frame=AsyncMock())
    host.tracker = Mock()
    handler = host._terminal_response_finished
    node = {
        "name": "closing",
        "role_message": "Goodbye {{name}}",
        "post_actions": [{"type": "function", "handler": handler, "node": "closing"}],
    }
    manager = object.__new__(TracedFlowManager)
    manager._current_node = "hot_followup"
    manager._classifier_runner = AsyncMock(return_value=None)
    manager._transition_tool_id = "closing-tool"
    manager.context_generation = 0
    manager._state = {"name": "Omkar"}
    manager._snapshot = {
        "contact_variables": ["name"],
        "flow": {"nodes": [{"id": "closing", "terminal": True}]},
    }
    manager.tracker = Mock()
    manager.termination = CallTermination()
    setup = AsyncMock()
    monkeypatch.setattr(FlowManager, "_set_node", setup)
    await manager._set_node("closing", node)
    rendered = setup.await_args.args[1]
    assert rendered["post_actions"][0]["handler"] is handler
    assert rendered["role_message"] == "Goodbye Omkar"
    assert node["role_message"] == "Goodbye {{name}}"
    assert manager.termination.summary.terminal_node == "closing"
    manager._current_node = "closing"
    await rendered["post_actions"][0]["handler"](rendered["post_actions"][0], manager)
    assert host.termination.summary.cause == "terminal_completed"
    host.worker.queue_frame.assert_awaited_once()
    manager.termination.summary.pipeline_finished_at_ns = 1
    assert manager.termination.summary.execution_status == "completed"
