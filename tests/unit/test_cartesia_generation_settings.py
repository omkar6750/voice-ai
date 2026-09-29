"""Provider-specific Cartesia controls must be validated and reach Pipecat."""

from types import SimpleNamespace

import pytest
import voice_runtime.execution.speech as speech_module
from pydantic import ValidationError
from voice_runtime.contracts.providers import TTSConfig
from voice_runtime.execution.native import build_speech_services


class _FakeService:
    class Settings:
        def __init__(self, **values):
            self.values = values

    def __init__(self, **values):
        self.values = values


def test_cartesia_settings_are_provider_specific_and_bounded():
    config = TTSConfig.model_validate(
        {
            "provider": "cartesia",
            "model": "sonic-3",
            "voice": "voice-id",
            "language": "en-US",
            "cartesia": {
                "generation_config": {"volume": 1.2, "speed": 0.9, "emotion": "calm"},
                "pronunciation_dict_id": "dictionary-id",
            },
        }
    )
    assert config.cartesia.generation_config.volume == 1.2
    assert config.cartesia.pronunciation_dict_id == "dictionary-id"

    with pytest.raises(ValidationError):
        TTSConfig(provider="sarvam", cartesia={"pronunciation_dict_id": "dictionary-id"})
    with pytest.raises(ValidationError):
        TTSConfig(provider="cartesia", model="sonic-3", pace=1.2)
    for invalid in ({"volume": 0.4}, {"speed": 1.6}, {"emotion": ""}):
        with pytest.raises(ValidationError):
            TTSConfig(
                provider="cartesia", model="sonic-3", cartesia={"generation_config": invalid}
            )


def test_cartesia_settings_reach_native_service(monkeypatch):
    monkeypatch.setattr(speech_module, "SarvamSTTService", _FakeService)
    monkeypatch.setattr(speech_module, "CartesiaTTSService", _FakeService)
    config = TTSConfig.model_validate(
        {
            "provider": "cartesia",
            "model": "sonic-3",
            "voice": "voice-id",
            "language": "en-US",
            "cartesia": {
                "generation_config": {"volume": 1.2, "speed": 0.9, "emotion": "calm"},
                "pronunciation_dict_id": "dictionary-id",
            },
        }
    )
    _, tts = build_speech_services(
        SimpleNamespace(sarvam_api_key="sarvam-key", cartesia_api_key="cartesia-key"),
        {"stt": {"provider": "sarvam", "model": "saaras:v3"}, "tts": config.model_dump(mode="json", exclude_none=True)},
        16000,
    )
    settings = tts.values["settings"].values
    assert settings["generation_config"].model_dump(exclude_none=True) == {
        "volume": 1.2,
        "speed": 0.9,
        "emotion": "calm",
    }
    assert settings["pronunciation_dict_id"] == "dictionary-id"
