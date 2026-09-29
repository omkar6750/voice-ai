"""The public identity route accepts only verified Clerk session tokens."""

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException, Request
from voice_api.api.v1.endpoints.agents import agents as list_agents
from voice_api.api.v1.endpoints.agents import create_agent
from voice_api.core.clerk_auth import ClerkPrincipal, require_clerk_user
from voice_api.core.clerk_organizations import (
    OrganizationMember,
    get_clerk_organization_directory,
)
from voice_api.core.security import (
    require_legacy_data_access,
    require_legacy_owner,
    require_organization_access,
    require_runtime_service,
)
from voice_api.db.session import get_session
from voice_api.main import app
from voice_api.models import Organization, PlatformAdministrator, PlatformSupportSession, User


def _request(method: str, path: str, *, member_allowed: bool = False) -> Request:
    endpoint = SimpleNamespace()
    if member_allowed:
        endpoint.__allow_organization_member__ = True
    route = SimpleNamespace(endpoint=endpoint)
    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "route": route,
            "headers": [],
        }
    )


def test_member_access_is_explicit_on_read_endpoints_and_defaults_to_admin() -> None:
    assert getattr(list_agents, "__allow_organization_member__", False)
    assert not getattr(create_agent, "__allow_organization_member__", False)


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
    ("user_id", "org_id", "db_owner", "allowed"),
    [
        ("user_123", "org_456", "local_user_1", True),
        ("user_other", "org_456", None, False),
        ("user_123", "org_other", None, False),
        ("user_123", None, None, False),
    ],
)
async def test_legacy_gate_uses_database_assignment(user_id, org_id, db_owner, allowed) -> None:
    class FakeSession:
        def __init__(self):
            self.sync_session = SimpleNamespace(info={}, identity_map={})

        async def scalar(self, statement):
            if "legacy_data_tenant" in str(statement):
                return db_owner
            if statement.column_descriptions[0]["entity"] is User:
                return None
            params = statement.compile().params
            assert params["clerk_org_id_1"] == org_id
            return db_owner

    class FakeDirectory:
        async def membership(self, requested_org, requested_user):
            assert requested_org == org_id
            assert requested_user == user_id
            return OrganizationMember(user_id, "org:member", None, None, None)

    previous = app.dependency_overrides.copy()
    app.dependency_overrides[require_clerk_user] = lambda: ClerkPrincipal(user_id, org_id)
    app.dependency_overrides[get_session] = lambda: FakeSession()
    app.dependency_overrides[get_clerk_organization_directory] = lambda: FakeDirectory()
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
async def test_registered_nonlegacy_org_binds_scope_for_member() -> None:
    class FakeSession:
        def __init__(self):
            self.sync_session = SimpleNamespace(info={}, identity_map={})

        async def scalar(self, statement):
            if statement.column_descriptions[0]["entity"] is User:
                return None
            assert "legacy_data_tenant" not in str(statement)
            assert statement.compile().params["clerk_org_id_1"] == "org_new"
            return "local_org_new"

    class FakeDirectory:
        async def membership(self, org_id, user_id):
            return OrganizationMember(user_id, "org:member", None, None, None)

    session = FakeSession()
    principal = await require_organization_access(
        _request("GET", "/api/v1/runs", member_allowed=True),
        ClerkPrincipal("user_new", "org_new"),
        session,
        FakeDirectory(),
    )
    assert principal.user_id == "user_new"
    assert session.sync_session.info["organization_scope_id"] == "local_org_new"


@pytest.mark.asyncio
async def test_locally_disabled_user_is_denied_despite_live_clerk_membership() -> None:
    class FakeSession:
        def __init__(self):
            self.sync_session = SimpleNamespace(info={}, identity_map={})

        async def scalar(self, statement):
            if statement.column_descriptions[0]["entity"] is User:
                return "disabled_user_row"
            return "registered_org"

    class FakeDirectory:
        async def membership(self, org_id, user_id):
            return OrganizationMember(user_id, "org:admin", None, None, None)

    session = FakeSession()
    with pytest.raises(HTTPException) as denied:
        await require_organization_access(
            _request("GET", "/api/v1/agents"),
            ClerkPrincipal("disabled_user", "org_1"),
            session,
            FakeDirectory(),
        )
    assert denied.value.status_code == 403
    assert session.sync_session.info.get("organization_scope_id") is None


@pytest.mark.asyncio
async def test_platform_support_session_scopes_as_database_assigned_admin() -> None:
    token = "short-lived-secret"

    class FakeSession:
        def __init__(self):
            self.sync_session = SimpleNamespace(info={}, identity_map={})
            self.record = SimpleNamespace(
                user_id="local_platform",
                organization_id="local_target_org",
                expires_at=datetime.now(UTC) + timedelta(minutes=10),
                revoked_at=None,
            )
            self.organization = SimpleNamespace(id="local_target_org", clerk_org_id="org_target")

        async def scalar(self, statement):
            if statement.column_descriptions[0]["entity"] is User:
                return "local_platform"
            if statement.column_descriptions[0]["entity"] is PlatformAdministrator:
                return 1
            raise AssertionError(f"Unexpected scalar query: {statement}")

        async def get(self, model, key):
            if model is PlatformSupportSession:
                assert key == sha256(token.encode()).hexdigest()
                return self.record
            if model is Organization:
                assert key == "local_target_org"
                return self.organization
            raise AssertionError(f"Unexpected get: {model}")

    class NoMembershipLookup:
        async def membership(self, *_args):
            raise AssertionError("Explicit support session must not rely on org membership")

    request = _request("GET", "/api/v1/agents", member_allowed=False)
    request.scope["headers"].append(
        (b"x-platform-support-session", token.encode("ascii"))
    )
    session = FakeSession()
    principal = await require_organization_access(
        request, ClerkPrincipal("platform_user", None), session, NoMembershipLookup()
    )
    assert principal.org_id == "org_target"
    assert session.sync_session.info["organization_scope_id"] == "local_target_org"
    assert request.state.platform_support_session == sha256(token.encode()).hexdigest()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["revoked", "expired", "unassigned"])
async def test_platform_support_session_fails_closed(failure) -> None:
    token = "short-lived-secret"

    class FakeSession:
        async def scalar(self, statement):
            if statement.column_descriptions[0]["entity"] is User:
                return "local_platform"
            if statement.column_descriptions[0]["entity"] is PlatformAdministrator:
                return None if failure == "unassigned" else 1
            raise AssertionError(f"Unexpected scalar query: {statement}")

        async def get(self, model, key):
            assert model is PlatformSupportSession
            assert key == sha256(token.encode()).hexdigest()
            return SimpleNamespace(
                user_id="local_platform",
                organization_id="target_org",
                expires_at=(
                    datetime.now(UTC) - timedelta(seconds=1)
                    if failure == "expired"
                    else datetime.now(UTC) + timedelta(minutes=1)
                ),
                revoked_at=datetime.now(UTC) if failure == "revoked" else None,
            )

    request = _request("GET", "/api/v1/agents")
    request.scope["headers"] = [(b"x-platform-support-session", token.encode())]
    with pytest.raises(HTTPException) as denied:
        await require_organization_access(
            request, ClerkPrincipal("platform_user", None), FakeSession(), object()
        )
    assert denied.value.status_code == 403


@pytest.mark.asyncio
async def test_legacy_access_remains_original_org_only() -> None:
    class FakeSession:
        def __init__(self):
            self.sync_session = SimpleNamespace(info={}, identity_map={})

        async def scalar(self, statement):
            if "legacy_data_tenant" in str(statement):
                return "local_original"
            if statement.column_descriptions[0]["entity"] is User:
                return None
            return "local_other"

    class FakeDirectory:
        async def membership(self, org_id, user_id):
            return OrganizationMember(user_id, "org:admin", None, None, None)

    with pytest.raises(HTTPException) as denied:
        await require_legacy_data_access(
            _request("GET", "/api/v1/auth/legacy-access", member_allowed=True),
            ClerkPrincipal("admin", "org_other"),
            FakeSession(),
            FakeDirectory(),
        )
    assert denied.value.status_code == 403


@pytest.mark.asyncio
async def test_runtime_token_cannot_authorize_legacy_owner(monkeypatch) -> None:
    monkeypatch.setattr(
        "voice_api.core.security.get_settings",
        lambda: SimpleNamespace(
            runtime_service_token="runtime-secret",
        ),
    )

    class FakeSession:
        async def scalar(self, statement):
            return None

    with pytest.raises(HTTPException) as denied:
        await require_legacy_owner(
            Request({"type": "http", "method": "GET", "path": "/", "headers": []}),
            ClerkPrincipal("other_1", "org_1"),
            FakeSession(),
        )
    assert denied.value.status_code == 403
    with pytest.raises(HTTPException) as missing:
        await require_runtime_service(None)
    assert missing.value.status_code == 401
    assert await require_runtime_service("runtime-secret") is None


@pytest.mark.asyncio
async def test_live_clerk_member_can_read_but_cannot_mutate_legacy_data() -> None:
    class FakeSession:
        def __init__(self):
            self.sync_session = SimpleNamespace(info={}, identity_map={})

        async def scalar(self, statement):
            if statement.column_descriptions[0]["entity"] is User:
                return None
            return "org_1"

    class FakeDirectory:
        def __init__(self, role):
            self.role = role

        async def membership(self, org_id, user_id):
            return OrganizationMember(user_id, self.role, None, None, None)

    principal = ClerkPrincipal("member_1", "org_1")
    read = _request("GET", "/api/v1/agents", member_allowed=True)
    write = _request("POST", "/api/v1/agents")
    assert await require_legacy_owner(read, principal, FakeSession(), FakeDirectory("org:member"))
    for path in (
        "/api/v1/auth/legacy-access",
        "/api/v1/runs/a8fb1d13-c650-4f55-a6bb-4d0150fd473e/timeline",
        "/api/v1/knowledge-bases/a8fb1d13-c650-4f55-a6bb-4d0150fd473e/chunks",
    ):
        reviewed_read = _request("GET", path, member_allowed=True)
        assert await require_legacy_owner(
            reviewed_read, principal, FakeSession(), FakeDirectory("org:member")
        )
    for path in ("/future-report", "/api/v1/dial-options", "/api/v1/tools/new-sensitive-data"):
        unknown_read = _request("GET", path)
        with pytest.raises(HTTPException) as blocked:
            await require_legacy_owner(
                unknown_read, principal, FakeSession(), FakeDirectory("org:member")
            )
        assert blocked.value.status_code == 403
    with pytest.raises(HTTPException) as denied:
        await require_legacy_owner(write, principal, FakeSession(), FakeDirectory("org:member"))
    assert denied.value.status_code == 403
    assert await require_legacy_owner(write, principal, FakeSession(), FakeDirectory("org:admin"))


@pytest.mark.asyncio
async def test_member_browser_call_exception_is_limited_to_session_lifecycle() -> None:
    class FakeSession:
        def __init__(self):
            self.sync_session = SimpleNamespace(info={}, identity_map={})

        async def scalar(self, statement):
            if statement.column_descriptions[0]["entity"] is User:
                return None
            return "org_1"

    class FakeDirectory:
        async def membership(self, org_id, user_id):
            return OrganizationMember(user_id, "org:member", None, None, None)

    principal = ClerkPrincipal("member_1", "org_1")
    session_id = "a8fb1d13-c650-4f55-a6bb-4d0150fd473e"
    allowed = [
        ("POST", "/api/v1/browser-sessions"),
        ("POST", f"/api/v1/browser-sessions/{session_id}/ticket"),
        ("DELETE", f"/api/v1/browser-sessions/{session_id}"),
    ]
    denied = [
        ("POST", "/api/v1/agents"),
        ("POST", "/api/v1/browser-sessions/bad/ticket"),
        ("POST", f"/api/v1/browser-sessions/{session_id}/other"),
        ("PATCH", f"/api/v1/browser-sessions/{session_id}"),
    ]
    for method, path in allowed:
        request = _request(method, path, member_allowed=True)
        assert await require_legacy_owner(request, principal, FakeSession(), FakeDirectory())
    for method, path in denied:
        request = _request(method, path)
        with pytest.raises(HTTPException) as blocked:
            await require_legacy_owner(request, principal, FakeSession(), FakeDirectory())
        assert blocked.value.status_code == 403


@pytest.mark.asyncio
async def test_runtime_and_dashboard_routes_reject_the_other_credential(monkeypatch) -> None:
    monkeypatch.setattr(
        "voice_api.core.security.get_settings",
        lambda: SimpleNamespace(
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
