import httpx
import pytest
from voice_runtime.execution.callback_http import CallbackHTTPError, post_callback_json


@pytest.mark.asyncio
async def test_post_callback_json_preserves_success_json_and_request() -> None:
    payload = {"slot_id": "slot-1", "reason": "requested"}
    requests: list[httpx.Request] = []

    async def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"status": "ok", "callback_id": "cb-1"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(respond), base_url="http://test"
    ) as client:
        result = await post_callback_json(client, "/book", payload, "operator-secret")

    assert result == {"status": "ok", "callback_id": "cb-1"}
    assert len(requests) == 1
    assert requests[0].headers["Authorization"] == "Bearer operator-secret"
    assert requests[0].read() == b'{"slot_id":"slot-1","reason":"requested"}'


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [302, 400, 401, 500])
async def test_post_callback_json_rejects_http_errors_without_body_leakage(
    status_code: int,
) -> None:
    secret_body = "operator-secret raw internal response"

    async def respond(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, text=secret_body)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(respond), base_url="http://test"
    ) as client:
        with pytest.raises(CallbackHTTPError) as error:
            await post_callback_json(client, "/book", {}, "operator-secret")

    assert error.value.status_code == status_code
    assert secret_body not in str(error.value)


@pytest.mark.asyncio
async def test_timeout_does_not_retry_a_possible_external_write() -> None:
    requests = []

    async def respond(request):
        requests.append(request)
        raise httpx.ReadTimeout("response unavailable", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(httpx.ReadTimeout):
            await post_callback_json(client, "https://example.test/book", {}, "fake-token")
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_malformed_success_json_is_not_silently_accepted_or_retried() -> None:
    requests = []

    async def respond(request):
        requests.append(request)
        return httpx.Response(200, text="not JSON")

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(ValueError):
            await post_callback_json(client, "https://example.test/book", {}, "fake-token")
    assert len(requests) == 1
