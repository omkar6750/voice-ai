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
                    "nodes": [
                        {"id": "end", "terminal": True, "prompt": "Call #missing now."}
                    ],
                },
            }
        )


def test_native_node_compiles_marker_without_changing_saved_prompt():
    saved = {
        "id": "opening",
        "prompt": "Call #change_node(node='closing').",
        "tool_bindings": ["change_node"],
        "respond_immediately": True,
        "context_strategy": "append",
        "terminal": False,
    }
    host = NativePipelineHost("test-run", Path("unused"), SimpleNamespace())
    host._nodes = {"opening": saved}
    host._snapshot = {
        "flow": {"initial_node": "opening"},
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
    assert node["task_messages"][0]["content"] == "Call change_node(node='closing')."
    assert saved["prompt"] == "Call #change_node(node='closing')."
