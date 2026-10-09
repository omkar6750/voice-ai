from unittest.mock import AsyncMock, Mock

import pytest
from voice_runtime.execution.flow_manager import TracedFlowManager
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
