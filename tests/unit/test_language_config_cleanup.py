"""Inactive caller-language switches must not remain in the agent contract."""

import pytest
from pydantic import ValidationError
from voice_runtime.contracts.agent import AgentConfig, LanguageConfig


def test_inactive_language_switches_are_not_part_of_contract():
    assert "follow_caller_language" not in LanguageConfig.model_fields
    assert "persist_requested_language" not in LanguageConfig.model_fields

    for field in ("follow_caller_language", "persist_requested_language"):
        with pytest.raises(ValidationError):
            LanguageConfig.model_validate({field: True})


def test_static_language_selection_remains_available():
    config = AgentConfig.model_validate(
        {
            "name": "Test",
            "language": {"default_language": "en-IN", "supported_languages": ["en-IN"]},
            "flow": {"initial_node": "end", "nodes": [{"id": "end", "terminal": True}]},
        }
    )
    assert config.language.default_language == "en-IN"
    assert config.tts.language == "en-IN"
