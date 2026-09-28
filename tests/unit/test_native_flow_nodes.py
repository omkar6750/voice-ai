from pathlib import Path
from types import SimpleNamespace

import pytest
from pipecat.flows import ContextStrategy, ContextStrategyConfig, NodeConfig
from pipecat.flows.types import FlowsFunctionSchema
from voice_runtime.execution.native import NativePipelineHost


def _host() -> NativePipelineHost:
    host = NativePipelineHost("test-run", Path("unused"), SimpleNamespace())
    host._snapshot = {
        "flow": {"initial_node": "opening"},
        "system_prompt": "Follow the system prompt.",
        "_resolved": {
            "tools": {
                "change_node": {
                    "definition": {
                        "description": "Move to an allowed node.",
                        "parameters": {
                            "type": "object",
                            "properties": {"node": {"type": "string"}},
                            "required": ["node"],
                        },
                    }
                }
            }
        },
    }
    host._nodes = {
        "opening": {
            "id": "opening",
            "prompt": "Ask whether they have a moment.",
            "tool_bindings": ["change_node"],
            "transitions": ["closing"],
            "respond_immediately": True,
            "context_strategy": "append",
        },
        "closing": {
            "id": "closing",
            "prompt": "Thank them and end the call.",
            "tool_bindings": [],
            "transitions": [],
            "respond_immediately": True,
            "context_strategy": "reset",
        },
    }
    return host


def test_saved_node_is_adapted_to_pipecat_node_config_and_function_schema():
    host = _host()

    node: NodeConfig = host._node("opening")

    assert node["name"] == "opening"
    assert node["role_message"] == "Follow the system prompt."
    assert node["task_messages"] == [
        {"role": "user", "content": "Ask whether they have a moment."}
    ]
    assert node["context_strategy"] == ContextStrategyConfig(
        strategy=ContextStrategy.APPEND
    )
    assert len(node["functions"]) == 1
    assert isinstance(node["functions"][0], FlowsFunctionSchema)
    assert node["functions"][0].name == "change_node"


@pytest.mark.asyncio
async def test_change_node_returns_native_node_config_only_for_saved_transition():
    host = _host()
    host.flow = SimpleNamespace(current_node="opening")
    handler = host._handler("change_node")

    result, next_node = await handler({"node": "closing"}, None)

    assert result == {"status": "ok", "node": "closing"}
    assert next_node["name"] == "closing"
    assert next_node["context_strategy"] == ContextStrategyConfig(
        strategy=ContextStrategy.RESET
    )
    assert await handler({"node": "unknown"}, None) == {
        "status": "error",
        "error": "Transition is not allowed",
    }
