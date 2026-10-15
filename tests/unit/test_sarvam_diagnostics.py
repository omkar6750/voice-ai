import json
from unittest.mock import AsyncMock

import pytest
from voice_runtime.execution.sarvam_stt import DiagnosticSarvamRealtimeSTTService


def service():
    return DiagnosticSarvamRealtimeSTTService(
        api_key="secret-test-key",
        sample_rate=16000,
        settings=DiagnosticSarvamRealtimeSTTService.Settings(model="saaras:v4"),
        keepalive_timeout=30,
    )


@pytest.mark.asyncio
async def test_keepalive_is_json_ping_and_sends_no_audio():
    stt = service()
    stt._send_json = AsyncMock(return_value=True)
    await stt._send_keepalive(b"unused-silence")
    stt._send_json.assert_awaited_once_with({"event": "ping"})
    assert stt.diagnostic_state["audio_bytes_sent"] == 0


@pytest.mark.asyncio
async def test_audio_counts_only_successfully_sent_chunks():
    stt = service()
    stt._websocket = object()
    stt._send_json = AsyncMock(side_effect=[False, True])
    events = []
    stt.diagnostic_event = lambda event, state: events.append((event, state))
    await stt._send_audio_chunk(bytes(640))
    assert stt.diagnostic_state["audio_bytes_sent"] == 0
    await stt._send_audio_chunk(bytes(640))
    assert stt.diagnostic_state["audio_bytes_sent"] == 640
    assert stt.diagnostic_state["audio_chunks_sent"] == 1
    assert events[0][0] == "first_audio_sent"
    assert "audio_input" not in json.dumps(events)


@pytest.mark.asyncio
async def test_provider_error_metadata_is_safe_and_unusable():
    stt = service()
    stt.push_error = AsyncMock()
    stt.set_usable = AsyncMock()
    await stt._handle_message(
        {
            "event": "error",
            "request_id": "req-safe-123",
            "code": 429,
            "message": "secret-test-key https://private.invalid?token=secret caller transcript",
        }
    )
    assert stt.diagnostic_state["provider_request_id"] == "req-safe-123"
    assert stt.diagnostic_state["http_status"] == 429
    assert stt.diagnostic_state["provider_error_code"] == "429"
    assert "secret" not in json.dumps(stt.diagnostic_state)
    stt.set_usable.assert_awaited_once_with(False)


def test_close_reason_is_normalized_not_copied():
    stt = service()

    class Closed(Exception):
        pass

    exc = Closed("secret-test-key caller words")
    exc.rcvd = type("Close", (), {"code": 1011, "reason": "secret-test-key"})()
    stt._capture_exception(exc)
    assert stt.diagnostic_state["websocket_close_code"] == 1011
    assert stt.diagnostic_state["exception_type"] == "Closed"
    assert "secret" not in json.dumps(stt.diagnostic_state)
