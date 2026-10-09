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


def test_removed_cadence_controls_are_ignored_for_legacy_drafts():
    config = SummarizerConfig.model_validate(
        {
            "enabled": True,
            "keywords": ["recap"],
            "compaction_threshold": 0.7,
            "preserve_opening_messages": 2,
        }
    )

    assert config.enabled is True
    assert not hasattr(config, "keywords")
    assert not hasattr(config, "compaction_threshold")


def test_null_exchange_cadence_uses_current_default_for_persisted_versions():
    config = SummarizerConfig.model_validate({"every_n_exchanges": None})

    assert config.every_n_exchanges == 4


def test_summarizer_defaults_to_separate_gemini_model_and_compact_memory():
    config = SummarizerConfig()

    assert config.model.provider == "gemini"
    assert config.model.max_tokens == 256
    assert config.model.temperature == 0.1
    assert config.every_n_exchanges == 4
    assert config.context_window_tokens == 3072
    assert config.output_budget_tokens == 256
    assert config.preserve_recent_exchanges == 2
    assert "field/value notes" in config.prompt


@pytest.mark.parametrize(("messages", "expected"), [(4, 2), (5, 3), (6, 3)])
def test_legacy_message_retention_is_converted_to_complete_exchanges(messages, expected):
    config = SummarizerConfig.model_validate({"preserve_recent_messages": messages})

    assert config.preserve_recent_exchanges == expected
