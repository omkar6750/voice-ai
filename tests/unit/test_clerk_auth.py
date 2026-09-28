"""The public identity route accepts only verified Clerk session tokens."""

from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException
from voice_api.core.clerk_auth import ClerkPrincipal, require_clerk_user
from voice_api.core.security import require_legacy_owner, require_runtime_service
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("email", "verification", "allowed"),
    [
        ("pawaromkar1654@gmail.com", "verified", True),
        ("someone@example.com", "verified", False),
        ("pawaromkar1654@gmail.com", "unverified", False),
    ],
)
async def test_legacy_owner_requires_verified_primary_email(
    monkeypatch, email, verification, allowed
) -> None:
    monkeypatch.setattr(
        "voice_api.core.security.get_settings",
        lambda: SimpleNamespace(
            clerk_legacy_owner_user_id=None,
            clerk_legacy_owner_email="pawaromkar1654@gmail.com",
            clerk_secret_key="test-secret",
        ),
    )

    class FakeClerk:
        def __init__(self, bearer_auth):
            assert bearer_auth == "test-secret"

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        @property
        def users(self):
            return self

        async def get_async(self, *, user_id):
            assert user_id == "user_123"
            return SimpleNamespace(
                primary_email_address_id="email_1",
                email_addresses=[
                    SimpleNamespace(
                        id="email_1",
                        email_address=email,
                        verification=SimpleNamespace(status=verification),
                    )
                ],
            )

    monkeypatch.setattr("voice_api.core.security.Clerk", FakeClerk)
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[require_clerk_user] = lambda: ClerkPrincipal("user_123", None)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/v1/auth/legacy-access")
        assert response.status_code == (204 if allowed else 403)
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


@pytest.mark.asyncio
async def test_runtime_token_cannot_authorize_legacy_owner(monkeypatch) -> None:
    monkeypatch.setattr(
        "voice_api.core.security.get_settings",
        lambda: SimpleNamespace(
            clerk_legacy_owner_user_id="owner_1",
            clerk_legacy_owner_email=None,
            runtime_service_token="runtime-secret",
        ),
    )
    with pytest.raises(HTTPException) as denied:
        await require_legacy_owner(ClerkPrincipal("other_1", None))
    assert denied.value.status_code == 403
    with pytest.raises(HTTPException) as missing:
        await require_runtime_service(None)
    assert missing.value.status_code == 401
    assert await require_runtime_service("runtime-secret") is None


@pytest.mark.asyncio
async def test_runtime_and_dashboard_routes_reject_the_other_credential(monkeypatch) -> None:
    monkeypatch.setattr(
        "voice_api.core.security.get_settings",
        lambda: SimpleNamespace(
            clerk_legacy_owner_user_id="owner_1",
            clerk_legacy_owner_email=None,
            runtime_service_token="runtime-secret",
        ),
    )
    monkeypatch.setattr(
        "voice_api.core.clerk_auth.get_settings",
        lambda: SimpleNamespace(
            clerk_secret_key="test-secret",
            clerk_authorized_parties="http://localhost:5173",
        ),
    )
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[require_clerk_user] = lambda: ClerkPrincipal("owner_1", None)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            runtime = await client.post("/api/v1/runs/run_1/claim", json={})
        assert runtime.status_code == 401
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        dashboard = await client.get(
            "/api/v1/providers", headers={"X-Voice-Runtime-Token": "runtime-secret"}
        )
    assert dashboard.status_code == 401
