from types import SimpleNamespace

import pytest
from voice_runtime.execution import classifier


def test_normalizer_removes_provider_padding_and_unknown_fields():
    result = classifier.normalize_classifier_result(
        {
            "lead_temperature": {"choice": "warm", "confidence": 0.91},
            "service_fit": "strong_fit",
            "tone": "receptive",
            "probabilities": {"warm": 0.91},
            "notes": "do not expose",
        }
    )
    assert result == {
        "lead_temperature": "warm",
        "service_fit": "strong_fit",
        "tone": "receptive",
    }


def test_normalizer_returns_bounded_error_for_invalid_or_oversized_output():
    assert classifier.normalize_classifier_result("not json") == classifier.DEFAULT_RESULT
    assert classifier.normalize_classifier_result(
        {"lead_temperature": "warm"}, {"lead_temperature": ["warm"]}, max_result_chars=5
    ) == classifier.DEFAULT_RESULT


@pytest.mark.asyncio
async def test_pipecat_runner_uses_public_context_and_provider_service(monkeypatch):
    captured = {}

    class FakeSettings:
        def __init__(self, **kwargs):
            captured["settings"] = kwargs

    class FakeService:
        Settings = FakeSettings

        def __init__(self, **kwargs):
            captured["service"] = kwargs

        async def run_inference(self, context, *, max_tokens):
            captured["messages"] = context.get_messages()
            captured["max_tokens"] = max_tokens
            return '{"lead_temperature":"warm","extra":"ignored"}'

    monkeypatch.setattr(classifier, "GroqLLMService", FakeService)
    result = await classifier.PipecatLLMClassifierRunner().run(
        settings=SimpleNamespace(groq_api_key="test"),
        config={
            "provider": "groq",
            "model": "test-model",
            "prompt": "Classify",
            "output_fields": {"lead_temperature": ["warm"]},
            "max_output_tokens": 96,
        },
        transcript="Caller: interested",
    )

    assert result == {"lead_temperature": "warm"}
    assert captured["messages"] == [{"role": "user", "content": "Caller: interested"}]
    assert captured["max_tokens"] == 96
    assert captured["settings"]["system_instruction"].startswith("Classify")
