import hashlib
import json
from uuid import uuid4

import httpx
import pytest
from voice_api.services.private_storage import (
    SupabasePrivateStorage,
    check_identity,
    object_identity,
    sanitized_diagnostics,
)


def test_identity_is_org_and_resource_bound():
    org, record = str(uuid4()), str(uuid4())
    key = object_identity(org, record, "documents", "a" * 64)
    check_identity(key, org, record, "documents")
    for other in [str(uuid4()), "../escaped"]:
        with pytest.raises(ValueError):
            check_identity(key, other, record, "documents")
    with pytest.raises(ValueError):
        check_identity(key, org, str(uuid4()), "documents")
    with pytest.raises(ValueError):
        check_identity(key, org, record, "diagnostics")


def test_diagnostics_rebuild_only_allowlisted_events():
    sentinel = "SECRET-SENTINEL-RAW-VENDOR-EXCEPTION"
    raw = (
        json.dumps(
            {
                "event": "pipeline_failed",
                "detail": sentinel,
                "url": sentinel,
                "count": 2,
                "error_category": "runtime",
            }
        )
        + "\n"
        + sentinel
        + "\n"
        + json.dumps({"event": sentinel, "count": 2})
    ).encode()
    safe = sanitized_diagnostics(raw)
    assert sentinel.encode() not in safe
    assert json.loads(safe.splitlines()[0]) == {
        "event": "pipeline_failed",
        "error_category": "runtime",
        "count": 2,
    }
    assert json.loads(safe.splitlines()[1]) == {"event": "untrusted_log"}


@pytest.mark.asyncio
async def test_private_bucket_is_verified_before_upload(monkeypatch):
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(200, json={"id": "voice-private", "public": True})

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs),
    )
    data = b"private document"
    key = object_identity(str(uuid4()), str(uuid4()), "documents", hashlib.sha256(data).hexdigest())
    storage = SupabasePrivateStorage(
        "https://example.supabase.co", "test-service-token", "voice-private"
    )
    with pytest.raises(ValueError, match="must be private"):
        await storage.upload(key, data)
    assert [r.method for r in requests] == ["GET"]


@pytest.mark.asyncio
async def test_upload_replay_never_overwrites_and_checks_exact_bytes(monkeypatch):
    requests = []
    data = b"private document"
    key = object_identity(str(uuid4()), str(uuid4()), "documents", hashlib.sha256(data).hexdigest())

    def handle(request):
        requests.append(request)
        if "/bucket/" in request.url.path:
            return httpx.Response(200, json={"id": "voice-private", "public": False})
        if request.method == "POST":
            assert request.headers["x-upsert"] == "false"
            assert request.content == data
            return httpx.Response(409)
        return httpx.Response(200, content=data)

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs),
    )
    storage = SupabasePrivateStorage(
        "https://example.supabase.co", "test-service-token", "voice-private"
    )
    assert await storage.upload(key, data) is None
    assert all(r.headers["authorization"] == "Bearer test-service-token" for r in requests)


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "https://user:secret@example.com",
        "https://example.com/redirect?key=secret",
    ],
)
def test_private_storage_requires_safe_origin(url):
    with pytest.raises(ValueError):
        SupabasePrivateStorage(url, "test", "voice-private")
