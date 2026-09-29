from voice_runtime.contracts import (
    is_registered_handler,
    registered_handler_names,
    registered_handler_specs,
    validate_node_actions,
)


def test_runtime_handler_registry_is_canonical_and_detached() -> None:
    specs = registered_handler_specs()
    names = {spec.name for spec in specs}

    assert names == set(registered_handler_names())
    assert {
        "change_node",
        "end_call",
        "send_whatsapp_template",
        "classify_lead",
        "query_knowledge_base",
    } <= names
    assert is_registered_handler("send_whatsapp_template")
    assert not is_registered_handler("missing_handler")

    specs[0].description = "mutated in test"
    assert registered_handler_specs()[0].description != "mutated in test"


def test_node_action_validation_only_allows_zero_required_input_end_call():
    config = {
        "background_hooks": [],
        "flow": {
            "nodes": [
                {"id": "greeting", "entry_actions": ["close"]},
            ]
        },
    }
    tools = {
        "close": {
            "kind": "registered",
            "handler": "end_call",
            "parameters": {"type": "object", "properties": {}, "required": []},
        }
    }
    assert validate_node_actions(config, tools) == []

    tools["close"]["handler"] = "classify_lead"
    assert validate_node_actions(config, tools) == [
        "Entry action 'close' on node 'greeting' is not supported by the live runtime"
    ]


def test_node_action_validation_keeps_background_hooks_unsupported():
    assert validate_node_actions({"background_hooks": ["close"], "flow": {"nodes": []}}, {}) == [
        "Background hooks are not supported by the live runtime"
    ]
