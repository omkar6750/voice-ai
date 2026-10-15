"""The public seed is a fixed evidence projection, never a tenant data export."""

import json
import re
from datetime import datetime

from voice_api.services.organization_demo import demo_agent_config, demo_fixture
from voice_runtime.contracts import AgentConfig


def test_demo_agent_is_valid_and_has_no_external_actions_or_hidden_stages():
    config = demo_agent_config()
    assert AgentConfig.model_validate(config.model_dump(mode="json")) == config
    assert config.tool_bindings == {}
    assert config.credential_refs == {}
    assert config.knowledge_base_ids == []
    assert config.background_hooks == []
    assert not config.classifier.enabled
    assert not config.composer.enabled
    assert not config.context.summarizer.enabled
    assert config.llm.fallback is None
    nodes = {node.id: node for node in config.flow.nodes}
    assert nodes["greeting"].task_messages
    assert nodes["project_pitch"].terminal is False
    assert nodes["project_qa"].terminal is False
    assert nodes["closing"].terminal
    assert nodes["closing"].post_actions == [{"type": "end_conversation"}]
    assert all("closing" in node.transitions for node in config.flow.nodes if not node.terminal)


def test_fixture_preserves_original_timing_and_excludes_private_payloads():
    fixture = demo_fixture()
    assert fixture["source_run_id"] == "f617e8b0-2e6c-487b-ac1e-69d251017d92"
    assert fixture["source_agent_version"] == 13
    assert fixture["run"]["status"] == "completed"
    assert len(fixture["messages"]) == 22
    assert len(fixture["exchanges"]) == 12
    assert len(fixture["spans"]) == 66
    assert [v["node_key"] for v in fixture["visits"]] == [
        "greeting",
        "project_pitch",
        "project_qa",
        "closing",
    ]
    assert "starter adaptation" in fixture["notice"]
    text = json.dumps(fixture)
    for private_key in (
        "api_key",
        "authorization",
        "credential_id",
        "connection_id",
        "contact_id",
        "org_id",
        "input_payload",
        "output_payload",
        "provider_message_id",
        "recording_path",
        "claim_token",
    ):
        assert f'"{private_key}"' not in text
    for message in fixture["messages"]:
        assert not re.search(r"(?<!\w)\+?\d[\d ()-]{6,}\d(?!\w)", message["content"])
        assert not re.search(
            r"\b(?:(?:zero|oh|one|two|three|four|five|six|seven|eight|nine|double|triple)[\s,-]+){6}",
            message["content"],
            re.IGNORECASE,
        )
    assert any("[phone number removed]" in m["content"] for m in fixture["messages"])
    start = datetime.fromisoformat(fixture["run"]["started_at"])
    end = datetime.fromisoformat(fixture["run"]["ended_at"])
    assert 200 < (end - start).total_seconds() < 220
    exchanges = {e["id"] for e in fixture["exchanges"]}
    spans = {s["id"] for s in fixture["spans"]}
    assert all(m["exchange_id"] in exchanges for m in fixture["messages"])
    assert all(s["parent_id"] is None or s["parent_id"] in spans for s in fixture["spans"])
    assert all(v["span_id"] in spans for v in fixture["visits"])


def test_fixture_loads_are_independent():
    first = demo_fixture()
    first["messages"][0]["content"] = "changed"
    assert demo_fixture()["messages"][0]["content"] != "changed"
