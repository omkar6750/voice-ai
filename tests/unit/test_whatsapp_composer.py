"""Composer contracts and transcript isolation; no provider or WhatsApp network calls."""

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from voice_api.services.provider_credentials import stage_providers
from voice_runtime.contracts.agent import AgentConfig, ComposerConfig
from voice_runtime.execution.exchange import ExchangeTracker
from voice_runtime.execution.native_host import NativePipelineHost
from voice_runtime.execution.whatsapp_composer import (
    ComposerError,
    ComposerProviderError,
    compose_whatsapp,
    composer_tool_schema,
    validate_composed_fields,
)

DEFINITION = {
    "description": "Send approved follow-up",
    "whatsapp": {"template_name": "dialtone_followup"},
    "parameters": {
        "type": "object",
        "properties": {
            "to": {"type": "string"},
            "caller_name": {"type": "string"},
            "message": {"type": "string"},
        },
    },
}


def test_main_agent_only_sees_optional_recipient():
    properties, required, description = composer_tool_schema(DEFINITION)
    assert list(properties) == ["to"]
    assert required == []
    assert "Do not supply message text" in description


def test_composer_rejects_missing_required_link_and_wrong_fields():
    with pytest.raises(ComposerError, match="required template URL"):
        validate_composed_fields(
            '{"message":"Thanks for speaking"}',
            fields=["message"],
            required_urls=["https://example.org/demo"],
        )
    with pytest.raises(ComposerError, match="pinned template"):
        validate_composed_fields(
            '{"message":"Hi","to":"919999999999"}',
            fields=["message"],
            required_urls=[],
        )


def test_plain_transcript_contains_only_finalized_speech():
    records = []
    tracker = ExchangeTracker("run-one", SimpleNamespace(submit=records.append))
    timestamp = datetime.now(UTC).isoformat()
    tracker.user_message("नमस्कार", timestamp)
    tracker.assistant_message("नमस्कार, कसे आहात?", timestamp)
    tracker.start_operation(
        "send_whatsapp", "tool", input_payload={"arguments": {"message": "hidden"}}
    )
    assert tracker.plain_transcript() == "Caller: नमस्कार\nAgent: नमस्कार, कसे आहात?"


@pytest.mark.asyncio
async def test_composer_receives_only_plain_transcript(monkeypatch):
    captured = {}

    class Service:
        async def run_inference(self, context, *, max_tokens):
            captured["messages"] = context.get_messages()
            captured["max_tokens"] = max_tokens
            return '{"caller_name":"there","message":"तुमच्या वेळेबद्दल धन्यवाद. Voice AI demo: https://example.org/demo"}'

    def build(_settings, _model, *, stage, system_instruction):
        captured["stage"] = stage
        captured["system"] = system_instruction
        return Service()

    monkeypatch.setattr("voice_runtime.execution.whatsapp_composer.build_llm_service", build)
    result = await compose_whatsapp(
        settings=object(),
        config={
            "model": {"provider": "groq", "model": "test", "max_tokens": 200},
            "timeout_secs": 5,
        },
        template={
            "system_prompt": "Write in the caller's language.",
            "required_urls": ["https://example.org/demo"],
        },
        definition=DEFINITION,
        transcript="Caller: मला demo पाहिजे\nAgent: मी link पाठवते",
    )
    assert result["message"].startswith("तुमच्या")
    assert result["caller_name"] == "there"
    assert captured["stage"] == "composer"
    assert captured["max_tokens"] == 200
    assert captured["messages"] == [
        {"role": "user", "content": "Caller: मला demo पाहिजे\nAgent: मी link पाठवते"}
    ]


def test_agent_composer_requires_bound_template_key():
    with pytest.raises(ValueError, match="composer prompt references an unbound tool"):
        AgentConfig.model_validate(
            {
                "name": "Test",
                "flow": {"initial_node": "start", "nodes": [{"id": "start", "terminal": True}]},
                "composer": {
                    "enabled": True,
                    "templates": {
                        "whatsapp_template_demo": {"system_prompt": "Write a follow-up."}
                    },
                },
            }
        )


def test_composer_credential_stage_is_selected_only_when_enabled():
    snapshot = {"composer": {"enabled": True, "model": {"provider": "groq"}}}
    assert stage_providers(snapshot)["composer"] == "groq"
    snapshot["composer"]["enabled"] = False
    assert "composer" not in stage_providers(snapshot)


@pytest.mark.parametrize(
    ("provider", "model", "reasoning_effort"),
    [
        ("groq", "qwen/qwen3.8-27b", "none"),
        ("gemini", "gemini-2.5-flash", "provider_default"),
        ("openrouter", "openai/gpt-4o-mini", "none"),
        ("sarvam", "sarvam-105b", "none"),
        ("isoquant", "glm-5.3-flash", "low"),
    ],
)
def test_composer_accepts_each_supported_llm_provider(provider, model, reasoning_effort):
    config = ComposerConfig.model_validate(
        {"model": {"provider": provider, "model": model, "reasoning_effort": reasoning_effort}}
    )
    assert config.model.provider == provider
    assert (
        stage_providers({"composer": {"enabled": True, "model": config.model.model_dump()}})[
            "composer"
        ]
        == provider
    )


def test_required_template_links_must_be_https():
    with pytest.raises(ValueError, match="public HTTPS"):
        AgentConfig.model_validate(
            {
                "name": "Test",
                "flow": {"initial_node": "start", "nodes": [{"id": "start", "terminal": True}]},
                "composer": {
                    "templates": {
                        "demo": {
                            "system_prompt": "Write a follow-up.",
                            "required_urls": ["http://example.org/demo"],
                        }
                    }
                },
            }
        )


def composer_host():
    host = NativePipelineHost("test-run", Path("unused"), SimpleNamespace())
    host._snapshot = {
        "composer": {
            "enabled": True,
            "model": {"provider": "groq", "model": "test", "max_tokens": 200},
            "templates": {
                "whatsapp_template_demo": {
                    "system_prompt": "Write a follow-up",
                    "required_urls": ["https://example.org/demo"],
                }
            },
        },
        "_resolved": {"tools": {"whatsapp_template_demo": {"definition": DEFINITION}}},
    }
    records = []
    host.tracker = ExchangeTracker("test-run", SimpleNamespace(submit=records.append))
    host.tracker.user_message("Please send me the demo", datetime.now(UTC).isoformat())
    host.broker = SimpleNamespace(tool=AsyncMock())
    manager = SimpleNamespace(active_tool_invocation_id="invocation-one", current_node="greeting")
    return host, manager, records


@pytest.mark.asyncio
async def test_composer_sends_validated_fields_after_composition(monkeypatch):
    host, manager, records = composer_host()
    composed = {"caller_name": "there", "message": "Voice AI demo: https://example.org/demo"}
    compose = AsyncMock(return_value=composed)
    monkeypatch.setattr("voice_runtime.execution.tool_dispatch.compose_whatsapp", compose)
    host.broker.tool.return_value = {"status": "accepted"}

    result = await host._handler("whatsapp_template_demo")({"to": "+919876543210"}, manager)

    assert result == {"status": "accepted"}
    host.broker.tool.assert_awaited_once_with(
        "whatsapp_template_demo", {"to": "+919876543210", **composed}, "invocation-one"
    )
    assert compose.await_args.kwargs["transcript"] == "Caller: Please send me the demo"
    span = next(
        record
        for record in records
        if record["kind"] == "span" and record["category"] == "composer"
    )
    assert span["status"] == "completed"
    assert span["attributes"]["tool_invocation_id"] == "invocation-one"
    assert span["input_payload"]["transcript"] == "Caller: Please send me the demo"
    assert span["output_payload"] == {"fields": composed}


@pytest.mark.asyncio
async def test_failed_composition_has_diagnostic_and_never_sends(monkeypatch):
    host, manager, records = composer_host()
    monkeypatch.setattr(
        "voice_runtime.execution.tool_dispatch.compose_whatsapp",
        AsyncMock(side_effect=ComposerError("Composer omitted a required template URL")),
    )

    result = await host._handler("whatsapp_template_demo")({}, manager)

    assert result["status"] == "error"
    assert result["_diagnostic"]["code"] == "composer_output_invalid"
    assert result["_diagnostic"]["metadata"]["tool_invocation_id"] == "invocation-one"
    assert any(record["kind"] == "span" and record["status"] == "failed" for record in records)
    host.broker.tool.assert_not_awaited()


@pytest.mark.asyncio
async def test_provider_failure_is_linked_to_composer_span(monkeypatch):
    host, manager, records = composer_host()
    try:
        raise ComposerProviderError("Composer provider request failed") from TimeoutError()
    except ComposerProviderError as failure:
        monkeypatch.setattr(
            "voice_runtime.execution.tool_dispatch.compose_whatsapp",
            AsyncMock(side_effect=failure),
        )
        result = await host._handler("whatsapp_template_demo")({}, manager)

    span = next(
        record
        for record in records
        if record["kind"] == "span" and record["category"] == "composer"
    )
    assert span["status"] == "failed"
    assert result["_diagnostic"]["metadata"]["operation_id"] == span["operation_id"]
    assert result["_diagnostic"]["metadata"]["operation"] == "composer"
    host.broker.tool.assert_not_awaited()
