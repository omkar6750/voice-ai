import json
from unittest.mock import AsyncMock

import pytest
from pipecat.services.sarvam.tts import TTS_MODEL_CONFIGS, SarvamTTSService
from pydantic import ValidationError
from voice_runtime.contracts.providers import SARVAM_V4_CATALOG, TTSConfig
from voice_runtime.execution.sarvam_tts import BulbulV4TTSService


def test_catalog_has_all_unique_published_personas():
    voices = SARVAM_V4_CATALOG["voices"]
    assert len(voices) == SARVAM_V4_CATALOG["count"] == 222
    assert len({voice["id"] for voice in voices}) == 222
    assert all(voice["name"] and voice["style"] and voice["language"] for voice in voices)


@pytest.mark.parametrize(
    "changes",
    [
        {"voice": "ritu"},
        {"language": "ml-IN"},
        {"pace": 3},
        {"sarvam": {"temperature": 0.6}},
        {"sarvam": {"pitch": 1}},
    ],
)
def test_invalid_v4_configuration_fails_before_network(changes):
    with pytest.raises(ValidationError):
        TTSConfig.model_validate(
            {"model": "bulbul:v4-flash", "voice": "simran_en_customer", **changes}
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("rate", [8000, 16000])
async def test_pinned_adapter_configuration_preserves_pcm_and_upstream_lifecycle(rate):
    models = dict(TTS_MODEL_CONFIGS)
    service = BulbulV4TTSService(
        api_key="test-not-real",
        sample_rate=rate,
        settings=SarvamTTSService.Settings(
            model="bulbul:v4-flash",
            voice="simran_en_customer",
            language="en-IN",
            pace=1.0,
            pitch=0.1,
            loudness=1.1,
            min_buffer_size=30,
            max_chunk_length=150,
        ),
    )
    service._websocket = AsyncMock()
    await service._send_config()
    payload = json.loads(service._websocket.send.call_args.args[0])["data"]
    assert "model=bulbul:v4-flash&send_completion_event=true" in service._websocket_url
    assert payload["speaker"] == "simran_en_customer"
    assert payload["speech_sample_rate"] == str(rate)
    assert payload["output_audio_codec"] == "linear16"
    assert payload["pitch"] == 0.1
    assert "temperature" not in payload and "model" not in payload
    assert TTS_MODEL_CONFIGS == models
    assert BulbulV4TTSService._receive_messages is SarvamTTSService._receive_messages
    assert BulbulV4TTSService._handle_interruption is SarvamTTSService._handle_interruption


def test_legacy_v3_unchanged():
    assert TTSConfig().model == "bulbul:v3"
    assert TTSConfig().voice == "ritu"
    assert TTSConfig().sarvam is None


def test_server_only_uses_external_finalized_transcript_strategy_without_local_analyzer(
    monkeypatch,
):
    from voice_runtime.execution import native_helpers

    def forbidden(*args, **kwargs):
        raise AssertionError("Local Smart Turn must not be constructed")

    monkeypatch.setattr(native_helpers, "LocalSmartTurnAnalyzerV3", forbidden)
    params = native_helpers.build_user_aggregator_params(
        {
            "stt": {
                "provider": "sarvam",
                "realtime": {"turn_timing": "server_only", "turn_stop_timeout_seconds": 3},
            },
            "call_limits": {"interruptions_enabled": True, "idle_timeout_secs": 60},
        },
        None,
    )
    assert params.vad_analyzer is None
    assert params.user_turn_stop_timeout == 3
    assert type(params.user_turn_strategies.stop[0]).__name__ == "ExternalUserTurnStopStrategy"


@pytest.mark.asyncio
async def test_v4_completion_and_stale_context_follow_upstream_handling():
    import base64

    from pipecat.frames.frames import TTSStoppedFrame

    service = BulbulV4TTSService(
        api_key="test-not-real",
        sample_rate=16000,
        settings=SarvamTTSService.Settings(
            model="bulbul:v4-flash", voice="simran_en_customer", language="en-IN", pace=1
        ),
    )

    class Socket:
        def __aiter__(self):
            return self.messages()

        async def messages(self):
            yield json.dumps(
                {
                    "type": "audio",
                    "data": {
                        "audio": base64.b64encode(bytes(640)).decode(),
                        "request_id": "req-test-123",
                    },
                }
            )
            yield json.dumps({"type": "event", "data": {"event_type": "final"}})

    service._websocket = Socket()
    service.get_active_audio_context_id = lambda: "current"
    service.audio_context_available = lambda context: context == "current"
    service.append_to_audio_context = AsyncMock()
    service.remove_audio_context = AsyncMock()
    service.stop_ttfb_metrics = AsyncMock()
    await service._receive_messages()
    assert service.diagnostic_state["provider_request_id"] == "req-test-123"
    assert isinstance(service.append_to_audio_context.await_args_list[-1].args[1], TTSStoppedFrame)
    service.remove_audio_context.assert_awaited_once_with("current")
    service.get_active_audio_context_id = lambda: None
    service.audio_context_available = lambda _: False
    service.remove_audio_context.reset_mock()
    await service._receive_messages()
    service.remove_audio_context.assert_not_awaited()
