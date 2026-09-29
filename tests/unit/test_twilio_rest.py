from __future__ import annotations

import asyncio
import base64

import httpx
import pytest
from voice_runtime.telephony.twilio import TwilioCredentials
from voice_runtime.telephony.twilio_rest import TwilioCallApiError, TwilioRestCall

ACCOUNT_SID = "AC" + "a" * 32
CALL_SID = "CA" + "b" * 32
TOKEN = "super-secret-token"
API_KEY_SID = "SK" + "c" * 32
API_KEY_SECRET = "api-key-secret"
URL = f"https://api.twilio.com/2010-04-01/Accounts/{ACCOUNT_SID}/Calls/{CALL_SID}.json"


def response(status: str = "completed", **overrides: object) -> httpx.Response:
    payload = {"sid": CALL_SID, "account_sid": ACCOUNT_SID, "status": status}
    payload.update(overrides)
    return httpx.Response(200, json=payload)


def make_call(client: httpx.AsyncClient, *, timeout_secs: float = 0.5) -> TwilioRestCall:
    return TwilioRestCall(
        TwilioCredentials(ACCOUNT_SID, TOKEN, API_KEY_SID, API_KEY_SECRET),
        CALL_SID,
        client=client,
        timeout_secs=timeout_secs,
    )


@pytest.mark.asyncio
async def test_complete_sends_authenticated_form_post_and_returns_status() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return response()

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await make_call(client).complete() == "completed"

    request = seen[0]
    assert request.method == "POST"
    assert str(request.url) == URL
    encoded_auth = base64.b64encode(f"{API_KEY_SID}:{API_KEY_SECRET}".encode()).decode()
    assert request.headers["authorization"] == f"Basic {encoded_auth}"
    assert request.headers["content-type"].startswith("application/x-www-form-urlencoded")
    assert request.content == b"Status=completed"


@pytest.mark.asyncio
async def test_status_get_returns_status() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return response("in-progress")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await make_call(client).status() == "in-progress"
    assert seen[0].method == "GET"
    assert str(seen[0].url) == URL


@pytest.mark.parametrize("sid", ["CA/../x", "CA" + "a" * 31, "AC" + "a" * 32, "CA" + "g" * 32])
def test_rejects_invalid_call_sid(sid: str) -> None:
    with pytest.raises(ValueError):
        TwilioRestCall(TwilioCredentials(ACCOUNT_SID, TOKEN, API_KEY_SID, API_KEY_SECRET), sid)


def test_rejects_invalid_account_sid() -> None:
    with pytest.raises(ValueError):
        TwilioRestCall(TwilioCredentials("AC/../x", TOKEN, API_KEY_SID, API_KEY_SECRET), CALL_SID)


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
def test_rejects_invalid_timeout(timeout: float) -> None:
    with pytest.raises(ValueError):
        TwilioRestCall(TwilioCredentials(ACCOUNT_SID, TOKEN, API_KEY_SID, API_KEY_SECRET), CALL_SID, timeout_secs=timeout)


@pytest.mark.asyncio
async def test_redirect_is_not_followed_and_is_sanitized() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(302, headers={"location": "https://attacker.invalid"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(TwilioCallApiError) as caught:
            await make_call(client).complete()
    assert calls == 1
    assert caught.value.http_status == 302
    assert not caught.value.write_uncertain
    assert TOKEN not in str(caught.value)


@pytest.mark.asyncio
async def test_http_error_does_not_include_response_body() -> None:
    secret_body = f"private detail {TOKEN}"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text=secret_body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(TwilioCallApiError) as caught:
            await make_call(client).complete()
    assert caught.value.http_status == 503
    assert caught.value.write_uncertain
    assert secret_body not in str(caught.value)


@pytest.mark.parametrize(
    "reply",
    [
        httpx.Response(200, content=b"not json"),
        httpx.Response(200, json=[]),
        httpx.Response(
            200, json={"sid": "wrong", "account_sid": ACCOUNT_SID, "status": "completed"}
        ),
        httpx.Response(
            200, json={"sid": CALL_SID, "account_sid": "AC" + "c" * 32, "status": "completed"}
        ),
        httpx.Response(
            200, json={"sid": CALL_SID, "account_sid": ACCOUNT_SID, "status": "mystery"}
        ),
    ],
)
@pytest.mark.asyncio
async def test_malformed_or_mismatched_reply_is_rejected(reply: httpx.Response) -> None:
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: reply)) as client:
        with pytest.raises(TwilioCallApiError):
            await make_call(client).status()


@pytest.mark.asyncio
async def test_outer_timeout_covers_stalled_mock_transport() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1)
        return response()

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(TwilioCallApiError) as caught:
            await make_call(client, timeout_secs=0.01).complete()
    assert caught.value.write_uncertain
    assert "timed out" in str(caught.value)


@pytest.mark.asyncio
async def test_write_is_not_retried() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("private network detail", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(TwilioCallApiError) as caught:
            await make_call(client).complete()
    assert calls == 1
    assert caught.value.write_uncertain
    assert "private network detail" not in str(caught.value)


@pytest.mark.asyncio
async def test_aclose_preserves_injected_client() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: response())
    ) as client:
        await make_call(client).aclose()
        assert not client.is_closed


@pytest.mark.asyncio
async def test_aclose_closes_owned_client() -> None:
    call = TwilioRestCall(TwilioCredentials(ACCOUNT_SID, TOKEN, API_KEY_SID, API_KEY_SECRET), CALL_SID)
    client = call._client
    await call.aclose()
    assert client.is_closed
