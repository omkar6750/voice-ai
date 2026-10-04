"""Connection reuse must not delay membership revocation."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from voice_api.core import clerk_client, clerk_organizations


@pytest.mark.asyncio
async def test_pool_reused_and_closed_on_shutdown(monkeypatch):
    monkeypatch.setattr(
        clerk_client, "get_settings", lambda: SimpleNamespace(clerk_secret_key="test-only")
    )
    first = clerk_client.get_clerk_clients()
    assert clerk_client.get_clerk_clients() is first
    assert first.http.timeout.read == 3
    await clerk_client.close_clerk_clients()
    assert first.http.is_closed and first.sync_http.is_closed
    assert clerk_client.get_clerk_clients.cache_info().currsize == 0


@pytest.mark.asyncio
async def test_membership_is_live_even_for_identical_requests(monkeypatch):
    entry = SimpleNamespace(
        role="org:admin", public_user_data=SimpleNamespace(user_id="user", identifier=None)
    )
    listing = AsyncMock(side_effect=[SimpleNamespace(data=[entry]), SimpleNamespace(data=[])])
    sdk = SimpleNamespace(organization_memberships=SimpleNamespace(list_async=listing))
    monkeypatch.setattr(clerk_organizations, "get_clerk_clients", lambda: SimpleNamespace(sdk=sdk))
    directory = clerk_organizations.ClerkOrganizationDirectory("test-only")
    assert (await directory.membership("org", "user")).role == "org:admin"
    assert await directory.membership("org", "user") is None
    assert listing.await_count == 2


@pytest.mark.asyncio
async def test_membership_failure_is_sanitized_and_not_cached(monkeypatch):
    listing = AsyncMock(side_effect=TimeoutError("private provider detail"))
    sdk = SimpleNamespace(organization_memberships=SimpleNamespace(list_async=listing))
    monkeypatch.setattr(clerk_organizations, "get_clerk_clients", lambda: SimpleNamespace(sdk=sdk))
    with pytest.raises(HTTPException) as error:
        await clerk_organizations.ClerkOrganizationDirectory("test-only").membership("org", "user")
    assert error.value.status_code == 503
    assert "private" not in error.value.detail
