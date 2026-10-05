"""Regression coverage for resolved speech settings passed to Pipecat services."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import voice_runtime.execution.native_helpers as native_helpers
import voice_runtime.execution.speech as speech_module
from voice_runtime.execution.native import build_speech_services


class _ServiceConstructor:
    def __init__(self, name):
        self.Settings = Mock(name=f"{name}.Settings", side_effect=lambda **values: values)
        self.construct = Mock(name=name)

    def __call__(self, **values):
        return self.construct(**values)


def _install_service_mocks(monkeypatch):
    stt = _ServiceConstructor("SarvamSTTService")
    sarvam_tts = _ServiceConstructor("SarvamTTSService")
    cartesia_tts = _ServiceConstructor("CartesiaTTSService")
    monkeypatch.setattr(speech_module, "SarvamSTTService", stt)
    monkeypatch.setattr(speech_module, "_WavChunkSarvamSTTService", stt)
    monkeypatch.setattr(speech_module, "SarvamTTSService", sarvam_tts)
    monkeypatch.setattr(speech_module, "CartesiaTTSService", cartesia_tts)
    return stt, sarvam_tts, cartesia_tts


def test_sarvam_settings_and_credentials_reach_service_constructors(monkeypatch):
    stt_mock, tts_mock, cartesia_mock = _install_service_mocks(monkeypatch)
    settings = SimpleNamespace(
        sarvam_api_key="sarvam-secret",
        cartesia_api_key="cartesia-secret-must-not-be-used",
    )

    build_speech_services(
        settings,
        {
            "stt": {"provider": "sarvam", "model": "saaras:v3"},
            "tts": {
                "provider": "sarvam",
                "model": "bulbul:v3",
                "voice": "anushka",
                "language": "hi-IN",
                "pace": 1.15,
            },
        },
        8000,
    )

    stt_mock.Settings.assert_called_once_with(model="saaras:v3")
    stt_mock.construct.assert_called_once_with(
        api_key="sarvam-secret", settings={"model": "saaras:v3"}, sample_rate=8000
    )
    tts_mock.Settings.assert_called_once_with(
        model="bulbul:v3", voice="anushka", language="hi-IN", pace=1.15
    )
    tts_mock.construct.assert_called_once_with(
        api_key="sarvam-secret",
        settings={
            "model": "bulbul:v3",
            "voice": "anushka",
            "language": "hi-IN",
            "pace": 1.15,
        },
        sample_rate=8000,
    )
    cartesia_mock.construct.assert_not_called()


def test_saaras_v4_uses_realtime_server_vad_and_codemix(monkeypatch):
    realtime = _ServiceConstructor("SarvamRealtimeSTTService")
    monkeypatch.setattr(speech_module, "SarvamRealtimeSTTService", realtime)
    _, _, _ = _install_service_mocks(monkeypatch)

    stt, _ = build_speech_services(
        SimpleNamespace(sarvam_api_key="sarvam-secret"),
        {
            "stt": {
                "provider": "sarvam",
                "model": "saaras:v4",
                "realtime": {
                    "language_code": "auto",
                    "mode": "codemix",
                    "stream_type": "fast",
                    "threshold": 0.3,
                    "silence_duration_ms": 500,
                    "min_speech_duration_ms": 250,
                    "prefix_padding_ms": 80,
                },
            },
            "call_limits": {"interruptions_enabled": False},
            "tts": {
                "provider": "sarvam",
                "model": "bulbul:v3",
                "voice": "ritu",
                "language": "en-IN",
                "pace": 1,
            },
        },
        16000,
    )

    realtime.Settings.assert_called_once_with(
        model="saaras:v4",
        language_code="auto",
        mode="codemix",
        stream_type="fast",
        threshold=0.3,
        silence_duration_ms=500,
        min_speech_duration_ms=250,
    )
    realtime.construct.assert_called_once_with(
        api_key="sarvam-secret",
        settings={
            "model": "saaras:v4",
            "language_code": "auto",
            "mode": "codemix",
            "stream_type": "fast",
            "threshold": 0.3,
            "silence_duration_ms": 500,
            "min_speech_duration_ms": 250,
        },
        sample_rate=16000,
        endpointing="vad",
        prefix_padding_ms=80,
        should_interrupt=False,
    )
    assert stt is realtime.construct.return_value


def test_realtime_server_vad_does_not_construct_local_smart_turn(monkeypatch):
    monkeypatch.setattr(
        native_helpers,
        "LocalSmartTurnAnalyzerV3",
        lambda: pytest.fail("Realtime must not construct local Smart Turn"),
    )

    params = native_helpers.build_user_aggregator_params(
        {
            "stt": {"provider": "sarvam", "model": "saaras:v4"},
            "call_limits": {"interruptions_enabled": True, "idle_timeout_secs": 60},
            "filter_incomplete_user_turns": False,
        },
        vad=object(),
    )

    assert type(params.user_turn_strategies.start[0]).__name__ == "ExternalUserTurnStartStrategy"
    assert type(params.user_turn_strategies.stop[0]).__name__ == "ExternalUserTurnStopStrategy"


def test_cartesia_settings_credentials_and_audio_format_reach_constructor(monkeypatch):
    stt_mock, sarvam_tts_mock, cartesia_mock = _install_service_mocks(monkeypatch)
    settings = SimpleNamespace(
        sarvam_api_key="sarvam-secret",
        cartesia_api_key="cartesia-secret",
    )
    generation = {"volume": 1.2, "speed": 0.9, "emotion": "calm"}

    _, tts = build_speech_services(
        settings,
        {
            "stt": {"provider": "sarvam", "model": "saaras:v3"},
            "tts": {
                "provider": "cartesia",
                "model": "sonic-3",
                "voice": "voice-id",
                "language": "en-US",
                "cartesia": {
                    "generation_config": generation,
                    "pronunciation_dict_id": "dictionary-id",
                },
            },
        },
        16000,
    )

    stt_mock.construct.assert_called_once()
    cartesia_mock.Settings.assert_called_once()
    args = cartesia_mock.Settings.call_args.kwargs
    assert args["model"] == "sonic-3"
    assert args["voice"] == "voice-id"
    assert args["language"] == "en-US"
    assert args["generation_config"].model_dump(exclude_none=True) == generation
    assert args["pronunciation_dict_id"] == "dictionary-id"
    cartesia_mock.construct.assert_called_once_with(
        api_key="cartesia-secret",
        settings=args,
        sample_rate=16000,
        encoding="pcm_s16le",
        container="raw",
    )
    assert tts is cartesia_mock.construct.return_value
    sarvam_tts_mock.construct.assert_not_called()


@pytest.mark.parametrize(
    ("slot", "provider", "message"),
    [
        ("stt", "cartesia", "Unsupported STT provider: cartesia"),
        ("tts", "unknown", "Unsupported TTS provider: unknown"),
    ],
)
def test_unsupported_provider_raises_without_constructing_wrong_service(
    monkeypatch, slot, provider, message
):
    stt_mock, sarvam_tts_mock, cartesia_tts_mock = _install_service_mocks(monkeypatch)
    snapshot = {
        "stt": {"provider": "sarvam", "model": "saaras:v3"},
        "tts": {"provider": "sarvam", "model": "bulbul:v3"},
    }
    snapshot[slot]["provider"] = provider

    with pytest.raises(ValueError, match=message):
        build_speech_services(SimpleNamespace(sarvam_api_key="fake-key"), snapshot, 16000)

    if slot == "stt":
        stt_mock.construct.assert_not_called()
    else:
        stt_mock.construct.assert_called_once()
    sarvam_tts_mock.construct.assert_not_called()
    cartesia_tts_mock.construct.assert_not_called()
