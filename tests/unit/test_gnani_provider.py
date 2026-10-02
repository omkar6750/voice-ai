"""Offline checks of Gnani selection, PCM framing, and safe failure propagation."""

from types import SimpleNamespace

import pytest
from voice_api.core.config import Settings
from voice_api.schemas.credentials import CredentialCreate
from voice_api.services.provider_credentials import stage_providers
from voice_api.services.provider_registry import get_provider_registry
from voice_runtime.contracts.providers import STTConfig, TTSConfig
from voice_runtime.diagnostics import provider_error_diagnostic
from voice_runtime.execution.gnani import RuntimeGnaniSTTService, RuntimeGnaniTTSService
from voice_runtime.execution.speech import build_speech_services


def snapshot():
    return {
        "stt": {"provider": "gnani", "model": "gnani-prisma-v2.5", "language": "hi-IN"},
        "tts": {
            "provider": "gnani",
            "model": "timbre-v2.5",
            "voice": "Nalini",
            "language": "hi-IN",
        },
        "classifier": {"enabled": False},
    }


@pytest.mark.parametrize("rate", [8000, 16000])
def test_stage_credentials_and_pcm_settings_reach_actual_plugin(rate):
    settings = SimpleNamespace(provider_stage_keys={"stt": "stt-secret", "tts": "tts-secret"})
    stt, tts = build_speech_services(settings, snapshot(), rate)
    assert isinstance(stt, RuntimeGnaniSTTService)
    assert isinstance(tts, RuntimeGnaniTTSService)
    assert stt._client.api_key == "stt-secret" and tts._client.api_key == "tts-secret"
    assert stt._settings.language.value == "hi-IN"
    assert tts._settings.model == "timbre-v2.5"
    assert tts._settings.voice == "Nalini"
    assert tts._audio_config.container == "raw"
    assert tts._audio_config.encoding == "linear_pcm"
    assert tts._audio_config.sample_width == 2
    assert tts._init_sample_rate == rate
    assert stage_providers(snapshot()) == {"stt": "gnani", "tts": "gnani"}


def test_invalid_model_language_voice_and_unsupported_speed_fail_before_network():
    with pytest.raises(ValueError, match="requires model"):
        STTConfig(provider="gnani")
    with pytest.raises(ValueError, match="language"):
        STTConfig(provider="gnani", model="gnani-prisma-v2.5", language="auto")
    with pytest.raises(ValueError, match="voice"):
        TTSConfig(provider="gnani", model="timbre-v2.5", voice="ritu")
    with pytest.raises(ValueError, match="pace"):
        TTSConfig(provider="gnani", model="timbre-v2.5", voice="Pranav", pace=1.2)
    with pytest.raises(ValueError, match="credential"):
        build_speech_services(SimpleNamespace(provider_stage_keys={}), snapshot(), 16000)


@pytest.mark.asyncio
async def test_real_time_pcm_is_reframed_without_loss_or_duplicate_send():
    stt, _ = build_speech_services(
        SimpleNamespace(provider_stage_keys={"stt": "s", "tts": "t"}), snapshot(), 8000
    )
    sent = []

    async def send(audio):
        sent.append(audio)

    stt._client = SimpleNamespace(send_audio=send)
    audio = bytes(range(256)) * 16
    for start in range(0, len(audio), 320):
        _ = [frame async for frame in stt.run_stt(audio[start : start + 320])]
    assert all(len(chunk) == 1024 for chunk in sent)
    assert b"".join(sent) == audio
    assert not stt._pcm_pending


@pytest.mark.asyncio
async def test_send_failure_is_not_reconnected_or_replayed(monkeypatch):
    stt, _ = build_speech_services(
        SimpleNamespace(provider_stage_keys={"stt": "s", "tts": "t"}), snapshot(), 8000
    )
    errors = []
    sends = []

    async def send(audio):
        sends.append(audio)
        raise ConnectionError("test failure")

    async def push_error(*args, **kwargs):
        errors.append({"error_msg": args[0] if args else kwargs.get("error_msg"), **kwargs})

    monkeypatch.setattr(stt, "push_error", push_error)
    stt._client = SimpleNamespace(send_audio=send)
    _ = [frame async for frame in stt.run_stt(b"\0" * 2048)]
    assert len(sends) == 1
    assert len(errors) == 1
    assert not stt._pcm_pending


@pytest.mark.asyncio
async def test_registry_and_write_only_credential_contract():
    registry = await get_provider_registry(
        Settings(_env_file=None, groq_api_key=None, gemini_api_key=None, gnani_api_key=None)
    )
    gnani = next(item for item in registry.providers if item.provider == "gnani")
    assert gnani.slots == ["stt", "tts"]
    assert gnani.models_by_slot["tts"] == ["timbre-v2.5"]
    assert any(voice.id == "Nalini" for voice in gnani.voices)
    assert gnani.status == "unconfigured"
    assert gnani.fields["pace"].runtime_supported
    assert "secret" not in registry.model_dump_json()
    credential = CredentialCreate(provider="gnani", name="Gnani key", api_key="gnani-test-token")
    assert "gnani-test-token" not in credential.model_dump_json()


def test_gnani_and_isoquant_credit_failures_are_coded():
    for provider in ("gnani", "isoquant"):
        diagnostic = provider_error_diagnostic(provider=provider, status_code=402)
        assert diagnostic["code"] == "provider_quota_exhausted"
        assert diagnostic["metadata"]["provider"] == provider
        assert diagnostic["retryable"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("complete", [True, False])
async def test_tts_json_pcm_alignment_and_expected_terminal_event(monkeypatch, complete):
    import json

    import gnani.tts.client as sdk
    from pipecat.frames.frames import TTSAudioRawFrame, TTSStoppedFrame

    sent, errors = [], []
    closed = False

    class Socket:
        async def send(self, body):
            sent.append(json.loads(body))

        async def close(self):
            nonlocal closed
            closed = True

        async def events(self):
            yield b"\x01\x02\x03"
            yield b"\x04"
            if complete:
                yield '{"type":"complete","request_id":"req-test"}'

        def __aiter__(self):
            return self.events()

    async def connect(url, **kwargs):
        assert url == "wss://api.vachana.ai/api/v1/tts"
        assert kwargs["additional_headers"]["X-API-Key-ID"] == "tts-secret"
        return Socket()

    async def noop(*args, **kwargs):
        pass

    async def error(*args, **kwargs):
        errors.append({"error_msg": args[0] if args else kwargs.get("error_msg"), **kwargs})

    monkeypatch.setattr(sdk.websockets, "connect", connect)
    _, tts = build_speech_services(
        SimpleNamespace(provider_stage_keys={"stt": "stt-secret", "tts": "tts-secret"}),
        snapshot(),
        8000,
    )
    for name in ("start_ttfb_metrics", "stop_ttfb_metrics", "start_tts_usage_metrics"):
        monkeypatch.setattr(tts, name, noop)
    monkeypatch.setattr(tts, "push_error", error)
    frames = [frame async for frame in tts.run_tts("Hello", "context-test")]
    assert closed
    assert sent[0]["model"] == "timbre-v2.5"
    assert sent[0]["language"] == "hi-IN"
    assert sent[0]["speed"] == 1.0
    assert sent[0]["audio_config"]["container"] == "raw"
    assert sent[0]["audio_config"]["sample_rate"] == 8000
    audio = [frame for frame in frames if isinstance(frame, TTSAudioRawFrame)]
    assert b"".join(frame.audio for frame in audio) == b"\x01\x02\x03\x04"
    assert all(frame.context_id == "context-test" for frame in audio)
    assert any(isinstance(frame, TTSStoppedFrame) for frame in frames) == complete
    assert bool(errors) != complete
    if errors:
        assert errors[0]["force_treat_as_permanent"] is True
        assert errors[0]["error_msg"] == "Gnani TTS failed"


@pytest.mark.asyncio
async def test_tts_interruption_closes_the_live_socket(monkeypatch):
    import asyncio

    import gnani.tts.client as sdk

    waiting, closed = asyncio.Event(), asyncio.Event()

    class Socket:
        async def send(self, body):
            pass

        async def close(self):
            closed.set()

        async def events(self):
            waiting.set()
            await asyncio.Event().wait()
            yield b"unreachable"

        def __aiter__(self):
            return self.events()

    async def connect(*args, **kwargs):
        return Socket()

    async def noop(*args, **kwargs):
        pass

    monkeypatch.setattr(sdk.websockets, "connect", connect)
    _, tts = build_speech_services(
        SimpleNamespace(provider_stage_keys={"stt": "s", "tts": "t"}), snapshot(), 16000
    )
    for name in ("start_ttfb_metrics", "stop_ttfb_metrics", "start_tts_usage_metrics"):
        monkeypatch.setattr(tts, name, noop)

    async def consume():
        return [frame async for frame in tts.run_tts("Hello", "context-test")]

    task = asyncio.create_task(consume())
    await asyncio.wait_for(waiting.wait(), timeout=2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert closed.is_set()


def test_wrapped_gnani_handshake_preserves_status_and_safe_request_id():
    import httpx
    from voice_runtime.diagnostics import provider_exception_diagnostic

    response = httpx.Response(401, headers={"x-request-id": "gnani-req-1"})
    error = Exception("safe wrapper")
    error.__cause__ = httpx.HTTPStatusError(
        "not persisted", request=httpx.Request("GET", "https://api.vachana.ai"), response=response
    )
    diagnostic = provider_exception_diagnostic(error, provider="gnani", operation="stt")
    assert diagnostic["code"] == "provider_authentication_failed"
    assert diagnostic["provider_request_id"] == "gnani-req-1"
    assert diagnostic["http_status"] == 401
    assert diagnostic["detail"] is None


@pytest.mark.asyncio
async def test_stt_sdk_transcripts_become_pipecat_frames_without_raw_payloads(monkeypatch):
    from gnani.stt import StreamTranscriptEvent
    from pipecat.frames.frames import InterimTranscriptionFrame, TranscriptionFrame

    stt, _ = build_speech_services(
        SimpleNamespace(provider_stage_keys={"stt": "s", "tts": "t"}), snapshot(), 16000
    )
    frames = []

    class Events:
        async def events(self):
            for final in (False, True):
                yield StreamTranscriptEvent(
                    text="नमस्ते",
                    audio_duration_ms=100,
                    segment_id="seg-1",
                    segment_index="1",
                    latency=100,
                    timestamp="",
                    raw={"is_final": final, "untrusted": "do not persist"},
                )

        def __aiter__(self):
            return self.events()

    async def push(frame):
        frames.append(frame)

    stt._client = Events()
    stt._closing = True
    monkeypatch.setattr(stt, "push_frame", push)
    await stt._receive_messages()
    assert isinstance(frames[0], InterimTranscriptionFrame)
    assert isinstance(frames[1], TranscriptionFrame)
    assert frames[1].text == "नमस्ते"
    assert frames[1].language.value == "hi-IN"
    assert frames[1].result is None
