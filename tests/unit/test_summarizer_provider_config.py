"""Summarizer model settings share the conversation LLM's provider contract."""

import pytest
from pydantic import ValidationError
from voice_runtime.contracts.cadence import SummarizerConfig


@pytest.mark.parametrize(
    ("provider", "reasoning"),
    [("groq", "none"), ("gemini", "provider_default")],
)
def test_summarizer_accepts_supported_llm_provider_settings(provider, reasoning):
    config = SummarizerConfig.model_validate(
        {
            "enabled": True,
            "model": {
                "provider": provider,
                "model": "test-model",
                "temperature": 0.2,
                "max_tokens": 256,
                "top_p": 0.9,
                "reasoning_effort": reasoning,
            },
        }
    )

    assert config.model.provider == provider
    assert config.model.model == "test-model"
    assert config.model.temperature == 0.2
    assert config.model.max_tokens == 256
    assert config.model.top_p == 0.9


def test_summarizer_rejects_provider_incompatible_reasoning():
    with pytest.raises(ValidationError, match="Gemini reasoning uses the provider default"):
        SummarizerConfig.model_validate(
            {"model": {"provider": "gemini", "reasoning_effort": "none"}}
        )
