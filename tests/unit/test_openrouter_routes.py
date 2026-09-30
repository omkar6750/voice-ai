from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from voice_api.api.v1.endpoints import openrouter


@pytest.mark.asyncio
async def test_openrouter_account_credential_lookup_requires_org_admin(monkeypatch):
    principal = SimpleNamespace(user_id="user_member")
    session = SimpleNamespace(sync_session=object(), scalar=AsyncMock())
    directory = object()
    organization = SimpleNamespace(id="local_org")
    member = SimpleNamespace(role="org:member")
    registered = AsyncMock(return_value=(organization, member))
    lookup = AsyncMock()
    def decrypt(*args, **kwargs):
        pytest.fail("member access must be denied before decrypt")

    monkeypatch.setattr(openrouter, "_registered_org", registered)
    monkeypatch.setattr(openrouter.credential_service, "lookup", lookup)
    monkeypatch.setattr(openrouter, "decrypt_provider_key", decrypt)

    with pytest.raises(HTTPException) as error:
        await openrouter._openrouter_client(
            "clerk_org", "credential_id", principal, session, directory, admin_required=True
        )

    assert error.value.status_code == 403
    lookup.assert_not_awaited()
    session.scalar.assert_not_awaited()


@pytest.mark.asyncio
async def test_openrouter_admin_account_credential_is_org_scoped_and_decrypted(monkeypatch):
    principal = SimpleNamespace(user_id="user_admin")
    session = SimpleNamespace(sync_session=object(), scalar=AsyncMock(return_value="user-row"))
    directory = object()
    organization = SimpleNamespace(id="local_org")
    member = SimpleNamespace(role="org:admin")
    row = SimpleNamespace(
        provider="openrouter",
        status="stored",
        ciphertext="encrypted",
        key_id="root-key-id",
    )
    monkeypatch.setattr(
        openrouter, "_registered_org", AsyncMock(return_value=(organization, member))
    )
    monkeypatch.setattr(openrouter, "bind_organization", lambda *_args: None)
    monkeypatch.setattr(openrouter.credential_service, "lookup", AsyncMock(return_value=row))
    monkeypatch.setattr(openrouter, "credential_scope", lambda _row: "org-bound-scope")
    def decrypt(*args, **kwargs):
        return "secret-value"
    monkeypatch.setattr(openrouter, "decrypt_provider_key", decrypt)

    client = await openrouter._openrouter_client(
        "clerk_org", "credential_id", principal, session, directory, admin_required=True
    )

    assert client._headers["Authorization"] == "Bearer secret-value"
    session.scalar.assert_awaited_once()


@pytest.mark.asyncio
async def test_openrouter_non_openrouter_credential_is_rejected(monkeypatch):
    principal = SimpleNamespace(user_id="user_member")
    session = SimpleNamespace(sync_session=object(), scalar=AsyncMock())
    row = SimpleNamespace(provider="groq", status="stored")
    monkeypatch.setattr(
        openrouter,
        "_registered_org",
        AsyncMock(
            return_value=(SimpleNamespace(id="local_org"), SimpleNamespace(role="org:member"))
        ),
    )
    monkeypatch.setattr(openrouter, "bind_organization", lambda *_args: None)
    monkeypatch.setattr(openrouter.credential_service, "lookup", AsyncMock(return_value=row))

    with pytest.raises(HTTPException) as error:
        await openrouter._openrouter_client(
            "clerk_org", "credential_id", principal, session, object()
        )

    assert error.value.status_code == 422
