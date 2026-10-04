"""Outbound diagnostics must not break authentication SDK requests or consume media."""

import httpx
import pytest
import requests

from voice_shared import http_clients


@pytest.fixture
def logged_transport(monkeypatch):
    # Register originals with monkeypatch before the instrumentation replaces them.
    monkeypatch.setattr(http_clients, "_installed", False)
    monkeypatch.setattr(httpx.AsyncClient, "send", httpx.AsyncClient.send)
    monkeypatch.setattr(httpx.Client, "send", httpx.Client.send)
    monkeypatch.setattr(requests.Session, "send", requests.Session.send)
    import httplib2

    monkeypatch.setattr(httplib2.Http, "request", httplib2.Http.request)
    events = []
    monkeypatch.setattr(http_clients, "enabled", lambda _: True)
    monkeypatch.setattr(http_clients, "emit", lambda event, **kwargs: events.append(event))
    http_clients.install("test")
    return events


async def test_async_get_signing_keys_and_json_post_survive_logging(logged_transport):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"keys": []}))
    ) as client:
        assert (await client.get("https://example.test/v1/jwks")).status_code == 200
        assert (
            await client.post("https://example.test/api", json={"api_key": "secret-canary"})
        ).status_code == 200
    assert len(logged_transport) == 2
    assert "secret-canary" not in str(logged_transport)


def test_sync_get_survives_outbound_logging(logged_transport):
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={}))
    ) as client:
        assert client.get("https://example.test/v1/jwks").status_code == 200
    assert len(logged_transport) == 1


def test_request_preview_does_not_read_unbuffered_stream():
    def chunks():
        raise AssertionError("Logging must not consume the stream")
        yield b"audio"

    request = httpx.Request("POST", "https://example.test/audio", content=chunks())
    assert http_clients.request_preview(request) == {"body": "[metadata-only]"}
