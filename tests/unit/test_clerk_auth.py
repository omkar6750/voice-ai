"""The public identity route accepts only verified Clerk session tokens."""

from types import SimpleNamespace

import httpx
import pytest
from voice_api.main import app


@pytest.mark.asyncio
async def test_clerk_me_requires_bearer_session(monkeypatch) -> None:
    monkeypatch.setattr(
        "voice_api.core.clerk_auth.get_settings",
        lambda: SimpleNamespace(
            clerk_secret_key="test-secret",
            clerk_authorized_parties="http://localhost:5173",
        ),
    )
    calls = []

    class FakeClerk:
        def __init__(self, bearer_auth):
            assert bearer_auth == "test-secret"

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def authenticate_request_async(self, request, options):
            calls.append(options)
            assert options.accepts_token == ["session_token"]
            assert options.authorized_parties == ["http://localhost:5173"]
            return SimpleNamespace(is_signed_in=False, payload=None)

    monkeypatch.setattr("voice_api.core.clerk_auth.Clerk", FakeClerk)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        missing = await client.get("/api/v1/auth/me")
        invalid = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer invalid"})
    assert missing.status_code == 401
    assert invalid.status_code == 401
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_clerk_me_returns_verified_identity(monkeypatch) -> None:
    monkeypatch.setattr(
        "voice_api.core.clerk_auth.get_settings",
        lambda: SimpleNamespace(
            clerk_secret_key="test-secret",
            clerk_authorized_parties="http://localhost:5173",
        ),
    )

    class FakeClerk:
        def __init__(self, bearer_auth):
            assert bearer_auth == "test-secret"

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def authenticate_request_async(self, request, options):
            assert request.headers["authorization"] == "Bearer verified"
            return SimpleNamespace(
                is_signed_in=True, payload={"sub": "user_123", "o": {"id": "org_456"}}
            )

    monkeypatch.setattr("voice_api.core.clerk_auth.Clerk", FakeClerk)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer verified"})
    assert response.status_code == 200
    assert response.json() == {"user_id": "user_123", "org_id": "org_456"}


@pytest.mark.asyncio
async def test_clerk_me_fails_closed_when_verifier_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(
        "voice_api.core.clerk_auth.get_settings",
        lambda: SimpleNamespace(
            clerk_secret_key="test-secret",
            clerk_authorized_parties="http://localhost:5173",
        ),
    )

    class FakeClerk:
        def __init__(self, bearer_auth):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def authenticate_request_async(self, request, options):
            raise RuntimeError("upstream secret or network error")

    monkeypatch.setattr("voice_api.core.clerk_auth.Clerk", FakeClerk)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer verified"})
    assert response.status_code == 503
    assert response.json() == {"detail": "Clerk verification unavailable"}
