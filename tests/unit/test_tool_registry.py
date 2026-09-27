from voice_runtime.contracts import (
    is_registered_handler,
    registered_handler_names,
    registered_handler_specs,
)


def test_runtime_handler_registry_is_canonical_and_detached() -> None:
    specs = registered_handler_specs()
    names = {spec.name for spec in specs}

    assert names == set(registered_handler_names())
    assert {
        "change_node",
        "end_call",
        "send_whatsapp_template",
        "classify_jev",
        "classify_llm",
        "query_knowledge_base",
    } <= names
    assert is_registered_handler("send_whatsapp_template")
    assert not is_registered_handler("missing_handler")

    specs[0].description = "mutated in test"
    assert registered_handler_specs()[0].description != "mutated in test"
