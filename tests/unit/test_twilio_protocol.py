import asyncio
import json

import pytest
from twilio.request_validator import RequestValidator
from voice_runtime.telephony.twilio_protocol import read_twilio_start, validate_twilio_signature

TOKEN = "current-primary-token"
ACCOUNT = "AC" + "1" * 32
CALL = "CA" + "2" * 32
STREAM = "MZ" + "3" * 32
RUN_ID = "run-123"
CORRELATION_ID = "correlation-456"
WS_URL = "wss://voice.example.test/api/v1/media"


class FakeWebSocket:
    def __init__(self, messages):
        self.messages = iter(messages)

    async def receive_text(self):
        item = next(self.messages)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, tuple):
            delay, value = item
            await asyncio.sleep(delay)
            item = value
        return json.dumps(item) if isinstance(item, dict) else item


def connected():
    return {"event": "connected", "protocol": "Call", "version": "1.0.0"}


def started(**overrides):
    start = {
        "accountSid": ACCOUNT,
        "callSid": CALL,
        "streamSid": STREAM,
        "mediaFormat": {"encoding": "audio/x-mulaw", "sampleRate": 8000, "channels": 1},
        "customParameters": {"run_id": RUN_ID, "correlation_id": CORRELATION_ID},
    }
    message = {"event": "start", "streamSid": STREAM, "start": start}
    for key, value in overrides.items():
        if key == "outer_streamSid":
            message["streamSid"] = value
        else:
            start[key] = value
    return message


def sign(url, token=TOKEN, params=None):
    return RequestValidator(token).compute_signature(url, params or {})


@pytest.mark.parametrize(
    "websocket,url", [(False, "https://voice.example.test/hook"), (True, WS_URL)]
)
def test_valid_twilio_signature(websocket, url):
    signature = sign(url)
    assert validate_twilio_signature(TOKEN, url, {}, signature, websocket=websocket)


def test_websocket_signature_accepts_only_documented_trailing_slash_fallback():
    assert validate_twilio_signature(TOKEN, WS_URL, {}, sign(WS_URL + "/"), websocket=True)
    assert not validate_twilio_signature(TOKEN, WS_URL, {}, sign(WS_URL + "//"), websocket=True)


def test_invalid_missing_and_old_token_signatures_fail():
    url = "https://voice.example.test/hook"
    assert not validate_twilio_signature(TOKEN, url, {}, "invalid")
    assert not validate_twilio_signature(TOKEN, url, {}, None)
    assert not validate_twilio_signature(TOKEN, url, {}, sign(url, "previous-token"))


@pytest.mark.parametrize(
    "url,websocket",
    [
        ("http://voice.example.test/hook", False),
        ("ws://voice.example.test/media", True),
        ("https://user:pass@voice.example.test/hook", False),
        ("https://voice.example.test/hook?x=1", False),
        ("https://voice.example.test/hook#fragment", False),
        ("https:///hook", False),
    ],
)
def test_noncanonical_or_unsafe_urls_are_rejected(url, websocket):
    assert not validate_twilio_signature(TOKEN, url, {}, sign(url), websocket=websocket)


async def valid_start(**overrides):
    return await read_twilio_start(
        FakeWebSocket([connected(), started(**overrides)]),
        account_sid=ACCOUNT,
        expected_call_sid=CALL,
        run_id=RUN_ID,
        correlation_id=CORRELATION_ID,
    )


@pytest.mark.asyncio
async def test_reads_valid_connected_and_start_messages():
    assert await valid_start() == (CALL, STREAM)


@pytest.mark.parametrize(
    "overrides",
    [
        {"callSid": None},
        {"streamSid": None},
        {"outer_streamSid": "MZ" + "4" * 32},
        {"accountSid": "AC" + "9" * 32},
        {"mediaFormat": {"encoding": "audio/pcm", "sampleRate": 8000, "channels": 1}},
        {"mediaFormat": {"encoding": "audio/x-mulaw", "sampleRate": 16000, "channels": 1}},
        {"customParameters": {"run_id": RUN_ID}},
        {
            "customParameters": {
                "run_id": RUN_ID,
                "correlation_id": CORRELATION_ID,
                "extra": "value",
            }
        },
    ],
)
@pytest.mark.asyncio
async def test_rejects_missing_or_mismatched_start_identity_and_format(overrides):
    with pytest.raises(ValueError, match="Invalid Twilio Media Stream"):
        await valid_start(**overrides)


@pytest.mark.asyncio
async def test_rejects_wrong_connected_protocol_and_unexpected_call_or_stream():
    with pytest.raises(ValueError, match="Invalid Twilio Media Stream"):
        await read_twilio_start(
            FakeWebSocket([{**connected(), "version": "2.0.0"}, started()]),
            account_sid=ACCOUNT,
            expected_call_sid=CALL,
            run_id=RUN_ID,
            correlation_id=CORRELATION_ID,
        )
    with pytest.raises(ValueError, match="Invalid Twilio Media Stream"):
        await read_twilio_start(
            FakeWebSocket([connected(), started()]),
            account_sid=ACCOUNT,
            expected_call_sid="CA" + "4" * 32,
            run_id=RUN_ID,
            correlation_id=CORRELATION_ID,
        )
    with pytest.raises(ValueError, match="Invalid Twilio Media Stream"):
        await read_twilio_start(
            FakeWebSocket([connected(), started()]),
            account_sid=ACCOUNT,
            expected_call_sid=None,
            expected_stream_sid="MZ" + "4" * 32,
            run_id=RUN_ID,
            correlation_id=CORRELATION_ID,
        )


@pytest.mark.asyncio
async def test_timeout_covers_both_handshake_reads():
    websocket = FakeWebSocket([connected(), (0.05, started())])
    with pytest.raises(TimeoutError, match="Timed out waiting for Twilio Media Stream handshake"):
        await read_twilio_start(
            websocket,
            account_sid=ACCOUNT,
            expected_call_sid=CALL,
            run_id=RUN_ID,
            correlation_id=CORRELATION_ID,
            timeout_secs=0.01,
        )


@pytest.mark.asyncio
async def test_malformed_message_error_does_not_echo_payload():
    payload = '{"secret":"do-not-leak"}'
    with pytest.raises(ValueError) as error:
        await read_twilio_start(
            FakeWebSocket([payload, started()]),
            account_sid=ACCOUNT,
            expected_call_sid=None,
            run_id=RUN_ID,
            correlation_id=CORRELATION_ID,
        )
    assert "do-not-leak" not in str(error.value)
