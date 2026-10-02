"""Node response operations must have their visit before Pipecat dispatches them."""

from unittest.mock import AsyncMock, Mock

import pytest
from pipecat.flows import FlowManager
from voice_runtime.execution.flow_manager import TracedFlowManager


@pytest.mark.parametrize("fail", [False, True])
async def test_visit_exists_before_response_dispatch_and_failed_setup_is_recorded(
    monkeypatch, fail
):
    flow = object.__new__(TracedFlowManager)
    flow._current_node = "prior"
    flow._classifier_runner = AsyncMock(return_value=None)
    flow._action_runner = AsyncMock(return_value=None)
    flow.tracker = Mock()
    flow._transition_tool_id = "tool-1"
    events = []
    flow.tracker.start_visit.side_effect = lambda *args: events.append("visit")

    async def dispatch(self, node_id, node_config):
        events.append("dispatch")
        if fail:
            raise RuntimeError("node failed")

    monkeypatch.setattr(FlowManager, "_set_node", dispatch)
    if fail:
        with pytest.raises(RuntimeError, match="node failed"):
            await flow._set_node("closing", {"task_messages": []})
        flow.tracker.end_visit.assert_called_once_with("failed")
    else:
        await flow._set_node("closing", {"task_messages": []})
        flow.tracker.end_visit.assert_not_called()
    assert events == ["visit", "dispatch"]
    flow.tracker.start_visit.assert_called_once_with("closing", "tool-1")
    assert flow._transition_tool_id is None
    assert [call.args for call in flow._classifier_runner.await_args_list] == [
        ("exit", "prior"),
        ("entry", "closing"),
    ]


async def test_classifier_order_does_not_run_legacy_custom_node_actions(
    monkeypatch,
):
    flow = object.__new__(TracedFlowManager)
    flow._current_node = "prior"
    flow._classifier_runner = AsyncMock(return_value=None)
    flow._action_runner = AsyncMock(return_value=None)
    flow._snapshot = {
        "flow": {
            "nodes": [
                {"id": "prior", "exit_actions": ["end_call"]},
                {"id": "closing", "entry_actions": ["end_call"]},
            ]
        }
    }
    flow.tracker = Mock()
    flow._transition_tool_id = None
    events = []
    flow._classifier_runner.side_effect = lambda phase, node: events.append(
        f"classifier:{phase}:{node}"
    )
    flow._action_runner.side_effect = lambda phase, node, key: events.append(
        f"action:{phase}:{node}:{key}"
    )

    async def dispatch(self, node_id, node_config):
        events.append(f"dispatch:{node_id}")

    monkeypatch.setattr(FlowManager, "_set_node", dispatch)
    await flow._set_node("closing", {})

    assert events == ["classifier:exit:prior", "classifier:entry:closing", "dispatch:closing"]
    flow._action_runner.assert_not_awaited()
