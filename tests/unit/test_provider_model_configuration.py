from types import SimpleNamespace

import pytest
import voice_runtime.execution.native as native_module
from voice_runtime.contracts import TTSConfig
from voice_runtime.execution.native import build_speech_services


class _FakeService:
    class Settings:
        def __init__(self, **values):
            self.values = values

    def __init__(self, **values):
        self.values = values


def test_snapshot_provider_values_reach_speech_service_constructors(monkeypatch):
    stt_service = type("FakeSTT", (_FakeService,), {})
    tts_service = type("FakeTTS", (_FakeService,), {})
    monkeypatch.setattr(native_module, "SarvamSTTService", stt_service)
    monkeypatch.setattr(native_module, "CartesiaTTSService", tts_service)

    stt, tts = build_speech_services(
        SimpleNamespace(sarvam_api_key="sarvam-key", cartesia_api_key="cartesia-key"),
        {
            "stt": {"provider": "sarvam", "model": "saaras:v3"},
            "tts": {
                "provider": "cartesia",
                "model": "sonic-3",
                "voice": "voice-id",
                "language": "en-US",
                "pace": 1.25,
            },
        },
        16000,
    )

    assert stt.values["settings"].values == {"model": "saaras:v3"}
    assert stt.values["api_key"] == "sarvam-key"
    assert tts.values["settings"].values == {
        "model": "sonic-3",
        "voice": "voice-id",
        "language": "en-US",
    }
    assert tts.values["api_key"] == "cartesia-key"
    assert tts.values["sample_rate"] == 16000


def test_tts_provider_and_model_must_match():
    with pytest.raises(ValueError, match="not supported by provider 'cartesia'"):
        TTSConfig(provider="cartesia", model="bulbul:v3")

    assert TTSConfig(provider="cartesia", model="sonic-3").model == "sonic-3"
