from __future__ import annotations

import json
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.websockets import WebSocketState
from twilio.request_validator import RequestValidator
from voice_api.api.deps import get_session
from voice_api.api.v1.endpoints import telephony
from voice_api.main import app
from voice_api.models import Call
from voice_runtime.telephony.twilio import TwilioCredentials

ACCOUNT, SID, STREAM = "AC" + "a" * 32, "CA" + "b" * 32, "MZ" + "c" * 32
BASE, CORR, RUN, TOKEN = "https://voice.example.com", "corr", "run", "fake-token"


def make_call():
    return Call(
        id="call",
        run_id=RUN,
        provider="twilio",
        telephony_connection_id="conn",
        provider_call_id=SID,
        status="dialing",
        provider_metadata={},
    )


@pytest.mark.parametrize("path", ["call-status", "stream-status"])
@pytest.mark.parametrize(
    "scenario,expected",
    [
        ("no_base", 403),
        ("wrong_account", 409),
        ("wrong_call", 409),
        ("no_signature", 403),
        ("valid", 204),
    ],
)
@pytest.mark.asyncio
async def test_callbacks_authenticate_configured_url_and_identity(path, scenario, expected):
    call = make_call()
    db = AsyncMock(spec=AsyncSession)
    db.get.return_value = call

    async def get_db():
        yield db

    app.dependency_overrides[get_session] = get_db
    data = {
        "AccountSid": ACCOUNT,
        "CallSid": SID,
        "CallStatus": "in-progress",
        "SequenceNumber": "2",
        "StreamSid": STREAM,
        "StatusCallbackEvent": "stream-started",
    }
    if scenario == "wrong_account":
        data["AccountSid"] = "AC" + "d" * 32
    if scenario == "wrong_call":
        data["CallSid"] = "CA" + "d" * 32
    url = f"{BASE}/api/v1/telephony/twilio/{path}/{CORR}"
    signature = RequestValidator(TOKEN).compute_signature(url, data)
    try:
        with (
            patch.object(telephony, "get_by_correlation_id", new=AsyncMock(return_value=call)),
            patch.object(
                telephony,
                "resolve_twilio_credentials",
                new=AsyncMock(return_value=(None, TwilioCredentials(ACCOUNT, TOKEN))),
            ),
            patch.object(
                telephony,
                "get_settings",
                return_value=SimpleNamespace(
                    public_base_url=None if scenario == "no_base" else BASE
                ),
            ),
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://untrusted-internal-host"
            ) as client:
                result = await client.post(
                    url.replace(BASE, ""),
                    data=data,
                    headers={
                        "X-Twilio-Signature": "" if scenario == "no_signature" else signature,
                        "X-Forwarded-Host": "attacker.invalid",
                    },
                )
        assert result.status_code == expected
        if expected != 204:
            db.commit.assert_not_awaited()
        elif path == "call-status":
            assert call.provider_metadata["twilio_sequence_number"] == 2
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("sequence", ["-1", "bad", "", "9" * 100])
@pytest.mark.asyncio
async def test_signed_invalid_callback_sequence_is_rejected(sequence):
    db = AsyncMock(spec=AsyncSession)

    async def get_db():
        yield db

    app.dependency_overrides[get_session] = get_db
    data = {
        "AccountSid": ACCOUNT,
        "CallSid": SID,
        "CallStatus": "completed",
        "SequenceNumber": sequence,
    }
    url = f"{BASE}/api/v1/telephony/twilio/call-status/{CORR}"
    try:
        with (
            patch.object(
                telephony, "get_by_correlation_id", new=AsyncMock(return_value=make_call())
            ),
            patch.object(
                telephony,
                "resolve_twilio_credentials",
                new=AsyncMock(return_value=(None, TwilioCredentials(ACCOUNT, TOKEN))),
            ),
            patch.object(
                telephony, "get_settings", return_value=SimpleNamespace(public_base_url=BASE)
            ),
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=BASE
            ) as client:
                response = await client.post(
                    url,
                    data=data,
                    headers={
                        "X-Twilio-Signature": RequestValidator(TOKEN).compute_signature(url, data)
                    },
                )
        assert response.status_code == 422
        db.commit.assert_not_awaited()
    finally:
        app.dependency_overrides.clear()


def websocket_setup(*, signature=True, custom=None, claim=True):
    call = make_call()
    db = AsyncMock(spec=AsyncSession)
    factory = Mock(return_value=AsyncMock())
    factory.return_value.__aenter__.return_value = db
    url = f"wss://voice.example.com/api/v1/telephony/twilio/media/{CORR}"
    ws = SimpleNamespace(
        headers={
            "x-twilio-signature": RequestValidator(TOKEN).compute_signature(url, {})
            if signature
            else "bad"
        },
        accept=AsyncMock(),
        close=AsyncMock(),
        send_json=AsyncMock(),
        application_state=WebSocketState.CONNECTED,
        client_state=WebSocketState.CONNECTED,
        receive_text=AsyncMock(
            side_effect=[
                json.dumps({"event": "connected", "protocol": "Call", "version": "1.0.0"}),
                json.dumps(
                    {
                        "event": "start",
                        "streamSid": STREAM,
                        "start": {
                            "accountSid": ACCOUNT,
                            "callSid": SID,
                            "streamSid": STREAM,
                            "mediaFormat": {
                                "encoding": "audio/x-mulaw",
                                "sampleRate": 8000,
                                "channels": 1,
                            },
                            "customParameters": {"run_id": RUN, "correlation_id": CORR}
                            if custom is None
                            else custom,
                        },
                    }
                ),
            ]
        ),
    )
    rest = SimpleNamespace(
        complete=AsyncMock(return_value="completed"),
        status=AsyncMock(return_value="completed"),
        aclose=AsyncMock(),
    )
    runtime = AsyncMock()
    claim_fn = AsyncMock(return_value={"audio": {"sample_rate": 8000}} if claim else None)
    stack = ExitStack()
    stack.enter_context(patch.object(telephony, "SessionFactory", factory))
    stack.enter_context(
        patch.object(telephony, "get_by_correlation_id", new=AsyncMock(return_value=call))
    )
    stack.enter_context(
        patch.object(
            telephony,
            "resolve_twilio_credentials",
            new=AsyncMock(return_value=(None, TwilioCredentials(ACCOUNT, TOKEN))),
        )
    )
    stack.enter_context(
        patch.object(telephony, "get_settings", return_value=SimpleNamespace(public_base_url=BASE))
    )
    stack.enter_context(patch.object(telephony, "TwilioRestCall", return_value=rest))
    stack.enter_context(patch.object(telephony, "claim_twilio_media", new=claim_fn))
    stack.enter_context(patch.object(telephony, "run_twilio_pipeline", new=runtime))

    async def fallback(**kwargs):
        kwargs["media"].termination.request("pipeline_failure")
        await kwargs["media"].close()

    stack.enter_context(
        patch.object(
            telephony, "finalize_twilio_startup_failure", new=AsyncMock(side_effect=fallback)
        )
    )
    return stack, ws, rest, runtime, claim_fn


@pytest.mark.asyncio
async def test_valid_media_wires_managed_transport_and_finally_hangs_up_once():
    stack, ws, rest, runtime, claim = websocket_setup()
    with stack:
        await telephony.twilio_media_endpoint(ws, CORR)
    ws.accept.assert_awaited_once()
    assert claim.await_count == 1
    assert claim.await_args.kwargs == {
        "call_id": "call",
        "run_id": RUN,
        "provider_call_id": SID,
        "stream_sid": STREAM,
    }
    args = runtime.await_args.kwargs
    assert args["transport"]._params.serializer.session is args["media"]
    assert args["transport"]._params.serializer._params.auto_hang_up is False
    assert args["transport"]._params.allowed_origins == []
    rest.complete.assert_awaited_once()
    rest.status.assert_awaited_once()
    ws.close.assert_awaited_once()


@pytest.mark.parametrize("scenario", ["signature", "custom", "duplicate"])
@pytest.mark.asyncio
async def test_rejected_media_never_starts_runtime_or_hangs_up_another_stream(scenario):
    stack, ws, rest, runtime, _ = websocket_setup(
        signature=scenario != "signature",
        custom={} if scenario == "custom" else None,
        claim=scenario != "duplicate",
    )
    with stack:
        await telephony.twilio_media_endpoint(ws, CORR)
    runtime.assert_not_awaited()
    rest.complete.assert_not_awaited()
    ws.close.assert_awaited_once_with(code=1008)
    if scenario == "signature":
        ws.accept.assert_not_awaited()


@pytest.mark.asyncio
async def test_runtime_setup_error_still_joins_rest_owner_and_closes_socket():
    stack, ws, rest, runtime, _ = websocket_setup()
    runtime.side_effect = RuntimeError("startup failed")
    with stack:
        await telephony.twilio_media_endpoint(ws, CORR)
    rest.complete.assert_awaited_once()
    rest.status.assert_awaited_once()
    ws.close.assert_awaited_once()
