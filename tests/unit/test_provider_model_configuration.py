from types import SimpleNamespace

import pytest
import voice_runtime.execution.speech as speech_module
from voice_runtime.contracts import STTConfig, TTSConfig
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
    monkeypatch.setattr(speech_module, "SarvamRealtimeSTTService", stt_service)
    monkeypatch.setattr(speech_module, "CartesiaTTSService", tts_service)

    stt, tts = build_speech_services(
        SimpleNamespace(sarvam_api_key="sarvam-key", cartesia_api_key="cartesia-key"),
        {
            "stt": {"provider": "sarvam", "model": "saaras:v3-realtime"},
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

    assert stt.values["settings"].values["model"] == "saaras:v3-realtime"
    assert stt.values["endpointing"] == "vad"
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


def test_saaras_v4_realtime_defaults_to_multilingual_server_vad():
    config = STTConfig(provider="sarvam", model="saaras:v4")

    assert config.realtime.language_code == "auto"
    assert config.realtime.mode == "codemix"
    assert config.realtime.stream_type == "fast"
    assert config.realtime.threshold == 0.3
    assert config.realtime.silence_duration_ms == 500
    assert config.realtime.min_speech_duration_ms == 250


def test_old_sarvam_snapshot_is_readable_but_cannot_be_saved():
    snapshot = {"provider": "sarvam", "model": "saaras:v3"}
    with pytest.raises(ValueError, match="requires model"):
        STTConfig.model_validate(snapshot)
    historic = STTConfig.model_validate(snapshot, context={"read_legacy_config": True})
    assert historic.model == "saaras:v3"
    assert snapshot["model"] == "saaras:v3"
