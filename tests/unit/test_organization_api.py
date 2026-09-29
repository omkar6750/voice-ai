"""Org explorer and invitation routes never trust a URL or role claim alone."""

from hashlib import sha256
from types import SimpleNamespace

import httpx
import pytest
from voice_api.core.clerk_auth import ClerkPrincipal, require_clerk_user
from voice_api.core.clerk_organizations import (
    JoinedOrganization,
    OrganizationMember,
    get_clerk_organization_directory,
)
from voice_api.db.session import get_session
from voice_api.main import app
from voice_api.models import (
    LegacyDataTenant,
    Organization,
    OrganizationAudit,
    OrganizationCreationClaim,
    PlatformAdministrator,
    PlatformSupportSession,
    User,
)


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class FakeSession:
    def __init__(self):
        self.orgs = {
            "org_a": SimpleNamespace(
                id="local_org_a", clerk_org_id="org_a", name="A", owner_user_id="local_a"
            ),
            "org_b": SimpleNamespace(
                id="local_org_b", clerk_org_id="org_b", name="B", owner_user_id="local_b"
            ),
        }
        self.user = SimpleNamespace(clerk_user_id="user_a", id="local_a")
        self.audit = []

    async def scalar(self, statement):
        entity = statement.column_descriptions[0]["entity"].__name__
        if "disabled_at IS NOT NULL" in str(statement):
            return None
        if entity == "User":
            user_id = statement.compile().params["clerk_user_id_1"]
            if user_id != "user_a":
                return None
            return (
                self.user.id if statement.column_descriptions[0]["expr"] is User.id else self.user
            )
        return self.orgs.get(statement.compile().params["clerk_org_id_1"])

    async def scalars(self, statement):
        return Rows(list(self.orgs.values()))

    def add(self, row):
        if isinstance(row, OrganizationAudit):
            self.audit.append(row)

    async def commit(self):
        return None

    async def rollback(self):
        return None


class FakeDirectory:
    def __init__(self, role="org:admin", removed=False):
        self.role = role
        self.removed = removed
        self.sent = []
        self.revoked = []

    async def joined(self, user_id):
        return [
            JoinedOrganization("org_a", "A", self.role),
            JoinedOrganization("org_b", "B", self.role),
            JoinedOrganization("org_unregistered", "Pending", "org:member"),
        ]

    async def membership(self, org_id, user_id):
        if self.removed or org_id != "org_a":
            return None
        return OrganizationMember(
            user_id, self.role if user_id == "user_a" else "org:member", None, None, None
        )

    async def members(self, org_id):
        return [
            OrganizationMember("user_a", self.role, "a@example.com", "A", None),
            OrganizationMember("user_b", "org:member", "b@example.com", "B", None),
        ]

    async def invitations(self, org_id):
        return [
            {
                "id": "inv_a",
                "email_address": "r@example.com",
                "role": "org:member",
                "status": "pending",
            }
        ]

    async def invite(self, org_id, inviter_id, email, role):
        self.sent.append((org_id, inviter_id, email, role))
        return {"id": "inv_new", "email_address": email, "role": role, "status": "pending"}

    async def revoke(self, org_id, invitation_id, requester_id):
        self.revoked.append((org_id, invitation_id, requester_id))

    async def change_role(self, org_id, user_id, role):
        self.sent.append((org_id, user_id, role))

    async def remove_member(self, org_id, user_id):
        self.revoked.append((org_id, user_id))

    async def verified_profile(self, user_id):
        return {
            "email": "a@example.com",
            "first_name": "Ada",
            "last_name": "Lovelace",
        }


@pytest.fixture
def org_overrides():
    directory = FakeDirectory()
    session = FakeSession()
    directory.session = session
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[require_clerk_user] = lambda: ClerkPrincipal("user_a", "org_a")
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_clerk_organization_directory] = lambda: directory
    yield directory
    app.dependency_overrides.clear()
    app.dependency_overrides.update(previous)


@pytest.mark.asyncio
async def test_org_explorer_lists_only_joined_orgs(org_overrides):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/orgs")
        foreign = await client.get("/api/v1/orgs/org_b")
    assert response.status_code == 200
    assert response.json() == [
        {"id": "org_a", "name": "A", "role": "org:admin", "is_owner": True, "registered": True},
        {"id": "org_b", "name": "B", "role": "org:admin", "is_owner": False, "registered": True},
        {
            "id": "org_unregistered",
            "name": "Pending",
            "role": "org:member",
            "is_owner": False,
            "registered": False,
        },
    ]
    assert foreign.status_code == 404


@pytest.mark.asyncio
async def test_admin_can_invite_and_revoke_but_not_foreign_org(org_overrides):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        created = await client.post(
            "/api/v1/orgs/org_a/invitations",
            json={"email_address": " Recruiter@Example.com ", "role": "org:member"},
        )
        foreign = await client.post(
            "/api/v1/orgs/org_b/invitations",
            json={"email_address": "r@example.com"},
        )
        invalid = await client.post(
            "/api/v1/orgs/org_a/invitations",
            json={"email_address": "r@example.com", "role": "platform:admin"},
        )
        revoked = await client.delete("/api/v1/orgs/org_a/invitations/inv_new")
    assert created.status_code == 201
    assert org_overrides.sent == [("org_a", "user_a", "recruiter@example.com", "org:member")]
    assert foreign.status_code == 404
    assert invalid.status_code == 422
    assert revoked.status_code == 204
    assert org_overrides.revoked == [("org_a", "inv_new", "user_a")]
    assert [item.action for item in org_overrides.session.audit] == [
        "invitation_created",
        "invitation_revoked",
    ]


@pytest.mark.asyncio
async def test_invitation_audit_failure_revokes_new_clerk_invitation(org_overrides):
    async def fail_commit():
        raise RuntimeError("simulated audit database failure")

    org_overrides.session.commit = fail_commit
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/orgs/org_a/invitations", json={"email_address": "r@example.com"}
        )
    assert response.status_code == 503
    assert org_overrides.revoked == [("org_a", "inv_new", "user_a")]


@pytest.mark.asyncio
async def test_member_and_removed_user_cannot_invite(org_overrides):
    org_overrides.role = "org:member"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        member = await client.post(
            "/api/v1/orgs/org_a/invitations", json={"email_address": "r@example.com"}
        )
        org_overrides.removed = True
        removed = await client.get("/api/v1/orgs/org_a/members")
    assert member.status_code == 403
    assert removed.status_code == 404
    assert not org_overrides.sent


@pytest.mark.asyncio
async def test_locally_disabled_org_member_is_denied(org_overrides):
    session = org_overrides.session
    scalar = session.scalar

    async def disabled_scalar(statement):
        if "disabled_at IS NOT NULL" in str(statement):
            return "local_a"
        return await scalar(statement)

    session.scalar = disabled_scalar
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/orgs/org_a/members")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_change_other_member_but_not_owner(org_overrides):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        changed = await client.patch(
            "/api/v1/orgs/org_a/members/user_b", json={"role": "org:admin"}
        )
        owner = await client.delete("/api/v1/orgs/org_a/members/user_a")
        foreign = await client.delete("/api/v1/orgs/org_b/members/user_b")
    assert changed.status_code == 204
    assert org_overrides.sent == [("org_a", "user_b", "org:admin")]
    assert [item.action for item in org_overrides.session.audit] == [
        "member_promoted_to_admin"
    ]
    assert owner.status_code == 409
    assert foreign.status_code == 404


@pytest.mark.asyncio
async def test_role_change_audit_failure_restores_previous_clerk_role(org_overrides):
    async def fail_commit():
        raise RuntimeError("simulated audit database failure")

    org_overrides.session.commit = fail_commit
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.patch(
            "/api/v1/orgs/org_a/members/user_b", json={"role": "org:admin"}
        )
    assert response.status_code == 503
    assert org_overrides.sent == [
        ("org_a", "user_b", "org:admin"),
        ("org_a", "user_b", "org:member"),
    ]


@pytest.mark.asyncio
async def test_owner_can_transfer_to_current_member_and_audit(org_overrides):
    class TransferSession:
        def __init__(self):
            self.org = SimpleNamespace(
                id="local_org_a", clerk_org_id="org_a", owner_user_id="local_a"
            )
            self.audit = []
            self.commits = 0

        async def scalar(self, statement):
            entity = statement.column_descriptions[0]["entity"]
            params = statement.compile().params
            if entity is Organization:
                return self.org if "clerk_org_id_1" in params else None
            if entity is User:
                user_id = params["clerk_user_id_1"]
                return SimpleNamespace(id="local_a" if user_id == "user_a" else "local_b")
            raise AssertionError(f"Unexpected query: {statement}")

        async def get(self, model, key, with_for_update=False):
            assert model is OrganizationCreationClaim
            return None

        async def flush(self):
            return None

        def add(self, row):
            if isinstance(row, OrganizationAudit):
                self.audit.append(row)

        async def commit(self):
            self.commits += 1

    session = TransferSession()
    app.dependency_overrides[get_session] = lambda: session
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/orgs/org_a/ownership-transfer", json={"user_id": "user_b"}
        )
    assert response.status_code == 200
    assert response.json() == {"organization_id": "org_a", "owner_user_id": "user_b"}
    assert session.org.owner_user_id == "local_b"
    assert session.commits == 1
    assert org_overrides.sent == [("org_a", "user_b", "org:admin")]
    assert len(session.audit) == 1
    assert isinstance(session.audit[0], OrganizationAudit)
    assert session.audit[0].action == "ownership_transferred"


@pytest.mark.asyncio
async def test_non_owner_cannot_transfer_ownership(org_overrides):
    class TransferSession:
        async def scalar(self, statement):
            entity = statement.column_descriptions[0]["entity"]
            if entity is Organization:
                return SimpleNamespace(id="local_org_a", owner_user_id="local_b")
            if entity is User:
                return SimpleNamespace(id="local_a")
            raise AssertionError(f"Unexpected query: {statement}")

    app.dependency_overrides[get_session] = lambda: TransferSession()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/orgs/org_a/ownership-transfer", json={"user_id": "user_b"}
        )
    assert response.status_code == 403
    assert not org_overrides.sent


@pytest.mark.asyncio
async def test_failed_owner_transfer_restores_clerk_role(org_overrides):
    class TransferSession:
        def __init__(self):
            self.org = SimpleNamespace(
                id="local_org_a", clerk_org_id="org_a", owner_user_id="local_a"
            )
            self.rollbacks = 0

        async def scalar(self, statement):
            entity = statement.column_descriptions[0]["entity"]
            params = statement.compile().params
            if entity is Organization:
                return self.org if "clerk_org_id_1" in params else None
            if entity is User:
                return SimpleNamespace(id="local_a" if params["clerk_user_id_1"] == "user_a" else "local_b")
            raise AssertionError(f"Unexpected query: {statement}")

        async def get(self, model, key, with_for_update=False):
            assert model is OrganizationCreationClaim
            return None

        async def flush(self):
            return None

        def add(self, _row):
            return None

        async def commit(self):
            raise RuntimeError("simulated database failure")

        async def rollback(self):
            self.rollbacks += 1

    session = TransferSession()
    app.dependency_overrides[get_session] = lambda: session
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/orgs/org_a/ownership-transfer", json={"user_id": "user_b"}
        )
    assert response.status_code == 503
    assert session.rollbacks == 1
    assert org_overrides.sent == [
        ("org_a", "user_b", "org:admin"),
        ("org_a", "user_b", "org:member"),
    ]


@pytest.mark.asyncio
async def test_account_capabilities_cover_any_registered_org(org_overrides):
    class AccountSession:
        async def execute(self, statement):
            return None

        async def scalars(self, statement):
            return Rows(
                [
                    SimpleNamespace(
                        id="local_org_a", clerk_org_id="org_a", owner_user_id="local_a"
                    ),
                    SimpleNamespace(
                        id="local_org_b", clerk_org_id="org_b", owner_user_id="local_b"
                    ),
                ]
            )

        async def scalar(self, statement):
            entity = statement.column_descriptions[0]["entity"]
            if entity is User:
                return SimpleNamespace(id="local_a")
            if entity is OrganizationCreationClaim:
                return "local_a"
            if entity is Organization:
                return "local_org_a"
            if entity is PlatformAdministrator:
                return "local_a"
            if entity is LegacyDataTenant:
                return "local_org_a"
            raise AssertionError(f"Unexpected query: {statement}")

        async def commit(self):
            return None

    app.dependency_overrides[get_session] = lambda: AccountSession()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/me")
    assert response.status_code == 200
    account = response.json()
    assert account["platform_admin"] is True
    assert account["can_create_org"] is False
    assert account["organizations"][0]["capabilities"] == [
        "read",
        "browser_test",
        "manage_members",
        "configure",
        "twilio_dial",
        "transfer_ownership",
    ]
    assert account["organizations"][1]["registered"] is True
    assert account["organizations"][1]["capabilities"] == [
        "read",
        "browser_test",
        "manage_members",
        "configure",
    ]
    assert account["organizations"][2]["registered"] is False
    assert account["organizations"][2]["capabilities"] == []


@pytest.mark.asyncio
async def test_platform_support_session_is_hashed_audited_and_revocable():
    class PlatformSession:
        def __init__(self):
            self.organization = SimpleNamespace(
                id="local_org_a", clerk_org_id="org_a", name="A", owner_user_id="local_a"
            )
            self.user = SimpleNamespace(
                id="local_a", clerk_user_id="user_a", first_name="Ada", last_name="A",
                disabled_at=None,
            )
            self.rows = []
            self.audit = []
            self.support = None

        async def scalar(self, statement):
            entity = statement.column_descriptions[0]["entity"]
            if entity is User:
                return self.user
            if entity is PlatformAdministrator:
                return 1
            if entity is Organization:
                return self.organization
            raise AssertionError(f"Unexpected scalar query: {statement}")

        async def execute(self, statement):
            return None

        async def get(self, model, key):
            assert model is PlatformSupportSession
            assert self.support.token_hash == key
            return self.support

        def add(self, row):
            if isinstance(row, PlatformSupportSession):
                self.support = row
                self.rows.append(row)
            elif isinstance(row, OrganizationAudit):
                self.audit.append(row)

        async def commit(self):
            return None

    session = PlatformSession()
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[require_clerk_user] = lambda: ClerkPrincipal("user_a", None)
    app.dependency_overrides[get_session] = lambda: session
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            started = await client.post("/api/v1/platform/orgs/org_a/support-session")
            token = started.json()["token"]
            ended = await client.delete(
                "/api/v1/platform/support-session",
                headers={"X-Platform-Support-Session": token},
            )
        assert started.status_code == 200
        assert ended.status_code == 204
        assert session.support.token_hash == sha256(token.encode()).hexdigest()
        assert session.support.revoked_at is not None
        assert [event.action for event in session.audit] == [
            "platform_support_started",
            "platform_support_ended",
        ]
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


@pytest.mark.asyncio
async def test_browser_api_cors_allows_configured_origin_only():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        allowed = await client.options(
            "/api/v1/platform/support-session",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "DELETE",
                "Access-Control-Request-Headers": "authorization,x-platform-support-session",
            },
        )
        foreign = await client.options(
            "/api/v1/orgs",
            headers={"Origin": "https://unrelated.example", "Access-Control-Request-Method": "GET"},
        )
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "x-platform-support-session" in allowed.headers.get(
        "access-control-allow-headers", ""
    ).lower()
    assert "access-control-allow-origin" not in foreign.headers
