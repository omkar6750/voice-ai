"""Named lifecycle, cross-org references and server leases on disposable PostgreSQL."""

from datetime import timedelta

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from voice_api.core.config import Settings
from voice_api.models import Agent, AgentVersion, Run
from voice_api.models.common import new_id, now
from voice_api.schemas.credentials import CredentialCreate, CredentialReplace
from voice_api.services import credential_service as credentials
from voice_api.services.credential_lease_service import acquire, issue
from voice_api.services.provider_credentials import resolve_references, settings_for_organization
from voice_api.services.vault_service import CredentialVault


@pytest.fixture
def encrypted_vault(monkeypatch):
    vault = CredentialVault({"root": Fernet.generate_key().decode()}, "root")
    monkeypatch.setattr(CredentialVault, "from_env", classmethod(lambda _: vault))
    return vault


async def make_run(database):
    agent = Agent(id=new_id(), name="Credential test " + new_id())
    database.add(agent)
    await database.flush()
    version = AgentVersion(id=new_id(), agent_id=agent.id, version=1, revision=1, status="draft", config={})
    database.add(version)
    await database.flush()
    run = Run(id=new_id(), channel="browser", transport_provider="dashboard", status="claimed", agent_version_id=version.id, resolved_config={})
    database.add(run)
    await database.flush()
    return run


async def test_named_replace_keeps_active_lease_delete_readd_revokes_without_rebinding(database, encrypted_vault):
    row = await credentials.store(database, CredentialCreate(name="Sales", provider="groq", api_key="old-secret"), "user-test")
    run = await make_run(database)
    await acquire(database, run.id)
    lease = await issue(database, run.id, row)
    await database.commit()
    replaced = await credentials.store(database, CredentialReplace(name="Sales", provider="groq", api_key="new-secret", expected_version=1), "user-test", credential_id=row.id)
    assert replaced.id == row.id and replaced.version == 2
    await database.refresh(lease)
    assert lease.revoked_at is None
    with pytest.raises(HTTPException) as error:
        await credentials.store(database, CredentialReplace(name="Sales", provider="groq", api_key="stale", expected_version=1), "user-test", credential_id=row.id)
    assert error.value.status_code == 409
    await credentials.remove(database, row.id, 2)
    await database.refresh(lease)
    assert lease.revoked_at is not None
    assert row.ciphertext == "" and row.status == "deleted"
    added = await credentials.store(database, CredentialCreate(name="Sales", provider="groq", api_key="readded"), "user-test")
    assert added.id != row.id
    safe = credentials.status(added).model_dump_json()
    assert not any(value in safe for value in ("readded", "ciphertext", "key_id", "root"))
    with pytest.raises(HTTPException):
        await resolve_references(database, {"llm": {"provider": "groq"}, "credential_refs": {"llm": row.id}, "classifier": {"enabled": False}})


async def test_multiple_named_keys_require_explicit_selection_and_no_legacy_env(database, encrypted_vault):
    first = await credentials.store(database, CredentialCreate(name="Agent key", provider="groq", api_key="one"), "user-test")
    await credentials.store(database, CredentialCreate(name="Classifier key", provider="groq", api_key="two"), "user-test")
    snapshot = {"llm": {"provider": "groq"}, "classifier": {"enabled": False}}
    with pytest.raises(HTTPException):
        await resolve_references(database, snapshot)
    snapshot["credential_refs"] = {"llm": first.id}
    assert (await resolve_references(database, snapshot))["llm"]["credential_id"] == first.id
    scoped = await settings_for_organization(database, first.org_id, Settings(_env_file=None, groq_api_key="deployment-sentinel", gemini_api_key="deployment-sentinel"))
    assert scoped.groq_api_key is None and scoped.gemini_api_key is None


async def test_global_admission_and_fixed_nonrenewing_lease(database, encrypted_vault):
    credential = await credentials.store(database, CredentialCreate(name="TTL key", provider="groq", api_key="ttl-key"), "user-test")
    run = await make_run(database)
    other = await make_run(database)
    await acquire(database, run.id)
    with pytest.raises(HTTPException) as error:
        await acquire(database, other.id)
    assert error.value.status_code == 409
    lease = await issue(database, run.id, credential)
    expires = lease.expires_at
    assert timedelta(seconds=419) < expires - now() <= timedelta(seconds=420)
    assert (await issue(database, run.id, credential)).expires_at == expires
    lease.expires_at = now() - timedelta(seconds=1)
    await database.flush()
    from voice_api.services.credential_lease_service import CredentialRevoked
    with pytest.raises(CredentialRevoked):
        await issue(database, run.id, credential)


async def test_database_credential_identity_is_immutable(database, encrypted_vault):
    row = await credentials.store(database, CredentialCreate(name="Identity", provider="groq", api_key="key"), "user-test")
    with pytest.raises(IntegrityError):
        async with database.begin_nested():
            await database.execute(text("UPDATE provider_credentials SET provider = 'gemini' WHERE id = :id AND org_id = :org_id"), {"id": row.id, "org_id": row.org_id})
