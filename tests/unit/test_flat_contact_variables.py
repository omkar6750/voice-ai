from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from voice_shared.contact_variables import normalize_contact_config, normalize_contact_prompt


@pytest.mark.asyncio
async def test_chat_snapshot_supplies_name_parts_for_flat_prompt_rendering(monkeypatch):
    from pipecat.flows.manager import FlowManager
    from voice_api.models import AgentVersion
    from voice_api.services import chat_service
    from voice_runtime.execution.contact_context import sanitize_contact_variables

    version = SimpleNamespace(id="version", status="draft", revision=1)
    contact = SimpleNamespace(
        id="caller",
        first_name="Omkar",
        last_name="Pawar",
        timezone="Asia/Kolkata",
        phone_number="+917304058886",
        business=None,
        source=None,
        language=None,
        metadata_json={},
    )
    snapshot = {
        "flow": {"initial_node": "greeting", "nodes": [{"id": "greeting"}]},
        "_resolved": {},
    }
    monkeypatch.setattr(chat_service, "resolve", AsyncMock(return_value=(snapshot, "hash")))
    session = SimpleNamespace(
        get=AsyncMock(side_effect=lambda model, key: version if model is AgentVersion else contact),
        add=lambda row: None,
        commit=AsyncMock(),
    )
    body = SimpleNamespace(
        agent_version_id="version",
        contact_id="caller",
        starting_node=None,
        caller_background=None,
        whatsapp_number=None,
        scenario="manual",
    )
    row = await chat_service.create(session, body)
    manager = object.__new__(FlowManager)
    manager._state = sanitize_contact_variables(
        row.contact_snapshot, ["first_name", "last_name", "business"]
    )
    node = {
        "role_message": normalize_contact_prompt("Hello {{ contact.first_name }} {{name}}"),
        "task_messages": [],
    }
    assert manager._render_node("greeting", node)["role_message"] == "Hello Omkar Omkar"
    assert "name" not in row.contact_snapshot
    assert "contact" not in manager.state


def test_aliases_are_translated_without_changing_other_text():
    assert (
        normalize_contact_prompt(
            "Name: {{name}} {{ contact.first_name }} {{contact.last_name}} {{contact.business}} {{caller_name}}"
        )
        == "Name: {{first_name}} {{first_name}} {{last_name}} {{business}} {{caller_name}}"
    )
    assert normalize_contact_prompt(r"\{{contact.name}}") == r"\{{contact.name}}"


def test_config_translation_preserves_original_and_deduplicates_variables():
    original = {
        "contact_variables": ["name", "first_name", "business"],
        "system_prompt": "{{name}}",
        "flow": {
            "nodes": [
                {
                    "role_message": "{{contact.business}}",
                    "task_messages": [{"role": "user", "content": "{{ contact.name }}"}],
                }
            ]
        },
    }
    result = normalize_contact_config(original)
    assert result["contact_variables"] == ["first_name", "business"]
    assert result["flow"]["nodes"][0]["role_message"] == "{{business}}"
    assert result["flow"]["nodes"][0]["task_messages"][0]["content"] == "{{first_name}}"
    assert original["system_prompt"] == "{{name}}"
