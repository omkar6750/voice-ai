"""Tests for the Clerk-native organization boundary."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Request
from voice_api.core.clerk_auth import ClerkPrincipal
from voice_api.core.clerk_organizations import OrganizationMember
from voice_api.core.security import require_organization_access


def _request(method: str, path: str, *, member_allowed: bool = False) -> Request:
    endpoint = SimpleNamespace()
    if member_allowed:
        endpoint.__allow_organization_member__ = True
    return Request({
        "type": "http",
        "method": method,
        "path": path,
        "route": SimpleNamespace(endpoint=endpoint),
        "headers": [],
    })


class FakeSession:
    def __init__(self):
        self.sync_session = SimpleNamespace(info={}, identity_map={})

    async def scalar(self, statement):
        if statement.column_descriptions[0]["entity"].__name__ == "User":
            return None
        return "local_org"


class FakeDirectory:
    def __init__(self, role="org:owner"):
        self.role = role

    async def membership(self, org_id, user_id):
        return OrganizationMember(user_id, self.role, None, None, None)


@pytest.mark.asyncio
async def test_owner_role_can_access_member_allowed_routes():
    principal = await require_organization_access(
        _request("GET", "/api/v1/agents", member_allowed=True),
        ClerkPrincipal("user_owner", "org_1", "org:owner"),
        FakeSession(),
        FakeDirectory(),
    )
    assert principal.org_role == "org:owner"


@pytest.mark.asyncio
async def test_member_role_cannot_access_unreviewed_routes():
    with pytest.raises(HTTPException):
        await require_organization_access(
            _request("GET", "/api/v1/credentials"),
            ClerkPrincipal("user_member", "org_1", "org:member"),
            FakeSession(),
            FakeDirectory("org:member"),
        )
