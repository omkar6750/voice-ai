from voice_api.api.v1.endpoints.tools import _remove_deleted_tool_references
from voice_runtime.contracts import AgentConfig


def test_delete_tool_removes_all_agent_config_references() -> None:
    raw_config = {
        "name": "Agent",
        "system_prompt": "Use #follow_up if requested. Keep the caller comfortable.",
        "tool_bindings": {
            "follow_up": {
                "tool_id": "whatsapp-id",
                "tool_version_id": "whatsapp-version",
            },
            "change_node": {"tool_id": "flow-id", "tool_version_id": "flow-version"},
        },
        "background_hooks": ["follow_up"],
        "flow": {
            "initial_node": "main",
            "nodes": [
                {
                    "id": "main",
                    "prompt": "Offer the catalog. If they agree, call #whatsapp_catalog.",
                    "role_prompt": "Use #follow_up for the approved template.",
                    "tool_bindings": ["follow_up", "change_node"],
                    "entry_actions": ["follow_up"],
                    "transitions": ["done"],
                },
                {
                    "id": "done",
                    "prompt": "Thank them.",
                    "tool_bindings": [],
                    "terminal": True,
                },
            ],
        },
    }

    cleaned, changed = _remove_deleted_tool_references(
        raw_config,
        tool_id="whatsapp-id",
        tool_version_ids={"whatsapp-version"},
        tool_name="whatsapp_catalog",
    )

    assert changed
    assert set(cleaned["tool_bindings"]) == {"change_node"}
    assert cleaned["background_hooks"] == []
    assert "#follow_up" not in cleaned["system_prompt"]
    assert "Keep the caller comfortable." in cleaned["system_prompt"]
    assert "#whatsapp_catalog" not in cleaned["flow"]["nodes"][0]["prompt"]
    assert "#follow_up" not in cleaned["flow"]["nodes"][0]["role_prompt"]
    assert cleaned["flow"]["nodes"][0]["tool_bindings"] == ["change_node"]
    assert cleaned["flow"]["nodes"][0]["entry_actions"] == []
    AgentConfig.model_validate(cleaned)
