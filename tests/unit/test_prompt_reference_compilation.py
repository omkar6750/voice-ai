"""Editor #tool markers are validated and removed before provider inference."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from voice_runtime.contracts.agent import AgentConfig
from voice_runtime.contracts.prompt_references import compile_tool_references
from voice_runtime.execution.native import NativePipelineHost


def test_only_bound_tool_markers_are_compiled():
    prompt = "Call #change_node(node='closing'). Keep #release_notes as literal text."
    assert compile_tool_references(prompt, {"change_node"}) == (
        "Call change_node(node='closing'). Keep #release_notes as literal text."
    )


def test_unbound_node_prompt_reference_is_rejected():
    with pytest.raises(ValidationError, match="unbound prompt tool references"):
        AgentConfig.model_validate(
            {
                "name": "Test",
                "flow": {
                    "initial_node": "end",
                    "nodes": [{"id": "end", "terminal": True, "prompt": "Call #missing now."}],
                },
            }
        )


def test_native_node_compiles_marker_without_changing_saved_prompt():
    saved = {
        "id": "opening",
        "prompt": "Call #go_to_closing().",
        "tool_bindings": [],
        "transitions": ["closing"],
        "respond_immediately": True,
        "context_strategy": "append",
        "terminal": False,
    }
    host = NativePipelineHost("test-run", Path("unused"), SimpleNamespace())
    host._nodes = {"opening": saved}
    host._snapshot = {
        "flow": {
            "initial_node": "opening",
            "nodes": [
                saved,
                {"id": "closing", "terminal": True, "transitions": [], "tool_bindings": []},
            ],
        },
        "system_prompt": "Follow the task.",
        "_resolved": {
            "tools": {
                "change_node": {
                    "definition": {
                        "description": "Move to an allowed node",
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
    node = host._node("opening")
    assert node["task_messages"] == []
    assert "Call go_to_closing()." in node["role_message"]
    assert saved["prompt"] == "Call #go_to_closing()."


@pytest.mark.parametrize("field", ["prompt", "role_message", "role_prompt", "task_messages"])
@pytest.mark.parametrize("nodes", [[], ["greeting"]])
def test_generated_fact_marker_is_valid_in_enabled_node(field, nodes):
    node = {"id": "greeting", "terminal": True}
    if field == "task_messages":
        node[field] = [{"role": "system", "content": "Call #record_recepient_name when given."}]
    else:
        node[field] = "Call #record_recepient_name when given."
    model = AgentConfig.model_validate(
        {
            "name": "Ritu",
            "fact_slots": [{"key": "recepient_name", "description": "Caller name", "nodes": nodes}],
            "flow": {"initial_node": "greeting", "nodes": [node]},
        }
    )
    assert model.fact_slots[0].key == "recepient_name"


def test_fact_marker_is_rejected_outside_selected_nodes_with_field_location():
    with pytest.raises(ValidationError) as error:
        AgentConfig.model_validate(
            {
                "name": "Ritu",
                "fact_slots": [
                    {"key": "recepient_name", "description": "Caller name", "nodes": ["closing"]}
                ],
                "flow": {
                    "initial_node": "greeting",
                    "nodes": [
                        {
                            "id": "greeting",
                            "role_message": "Call #record_recepient_name",
                            "transitions": ["closing"],
                        },
                        {"id": "closing", "terminal": True},
                    ],
                },
            }
        )
    assert error.value.errors()[0]["loc"] == ("flow", "nodes", 0, "role_message")


@pytest.mark.parametrize("allowed", [True, False])
def test_generated_transition_marker_requires_direct_transition(allowed):
    config = {
        "name": "Ritu",
        "flow": {
            "initial_node": "greeting",
            "nodes": [
                {
                    "id": "greeting",
                    "role_message": "If refused, call #go_to_closing.",
                    "transitions": ["closing"] if allowed else [],
                    "functions": [
                        {
                            "name": "route_result",
                            "description": "Route to closing",
                            "transition_to": "closing",
                            "transition_only": True,
                        }
                    ],
                },
                {"id": "closing", "terminal": True},
            ],
        },
    }
    if allowed:
        assert AgentConfig.model_validate(config).flow.nodes[0].role_message
    else:
        with pytest.raises(ValidationError) as error:
            AgentConfig.model_validate(config)
        assert error.value.errors()[0]["type"] == "unbound_prompt_tool"
