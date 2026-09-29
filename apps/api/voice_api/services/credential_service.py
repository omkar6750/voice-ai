"""Named credentials, optimistic replacement and transactional run revocation."""

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from voice_api.db.tenant_scope import required_organization
from voice_api.models import CredentialLease, ProviderCredential
from voice_api.models.common import new_id, now
from voice_api.schemas.credentials import (
    CredentialCreate,
    CredentialRename,
    CredentialReplace,
    CredentialStatus,
)
from voice_api.services.vault_service import CredentialVault, SecretScope, VaultError


def credential_scope(row: ProviderCredential) -> SecretScope:
    return SecretScope(row.org_id, row.id, row.provider, row.purpose, row.version)


def status(row: ProviderCredential) -> CredentialStatus:
    state = row.status
    if state != "deleted":
        try:
            CredentialVault.from_env().decrypt(row.ciphertext, row.key_id, scope=credential_scope(row))
        except VaultError:
            state = "unavailable"
    return CredentialStatus(id=row.id, name=row.name, provider=row.provider, purpose=row.purpose,
        version=row.version, status=state, configured=state == "stored",
        updated_at=row.updated_at, deleted_at=row.deleted_at)


async def lookup(session: AsyncSession, credential_id: str, *, lock: bool = False) -> ProviderCredential:
    org_id = required_organization(session.sync_session)
    row = await session.scalar(select(ProviderCredential).where(
        ProviderCredential.id == credential_id, ProviderCredential.org_id == org_id,
    ).with_for_update() if lock else select(ProviderCredential).where(
        ProviderCredential.id == credential_id, ProviderCredential.org_id == org_id,
    ))
    if row is None:
        raise HTTPException(404, "Credential not found")
    return row


async def revoke(session: AsyncSession, credential_id: str) -> None:
    await session.execute(update(CredentialLease).where(
        CredentialLease.credential_id == credential_id, CredentialLease.revoked_at.is_(None)
    ).values(revoked_at=now()))


async def store(session: AsyncSession, body: CredentialCreate, actor: str,
                *, credential_id: str | None = None) -> ProviderCredential:
    org_id = required_organization(session.sync_session)
    if credential_id:
        row = await lookup(session, credential_id, lock=True)
        if row.status == "deleted":
            raise HTTPException(409, "Deleted credentials cannot be restored; add a new credential")
        if not isinstance(body, CredentialReplace) or row.version != body.expected_version:
            raise HTTPException(409, "Credential changed; reload before replacing")
        if body.provider != row.provider:
            raise HTTPException(422, "Credential provider cannot change")
        row.version += 1
    else:
        row = ProviderCredential(id=new_id(), org_id=org_id, provider=body.provider,
            purpose={"twilio": "twilio_voice", "whatsapp": "whatsapp_cloud"}.get(body.provider, "api_key"),
            version=1, status="stored")
        session.add(row)
    row.name = body.name.strip()
    row.updated_by_clerk_user_id = actor
    try:
        encrypted = CredentialVault.from_env().encrypt(body.plaintext(), scope=credential_scope(row))
    except VaultError as error:
        raise HTTPException(503, "Credential encryption is unavailable") from error
    row.ciphertext, row.key_id = encrypted.ciphertext, encrypted.key_id
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise HTTPException(409, "Credential name is already in use") from error
    return row


async def remove(session: AsyncSession, credential_id: str, expected_version: int) -> None:
    row = await lookup(session, credential_id, lock=True)
    if row.version != expected_version:
        raise HTTPException(409, "Credential changed; reload before deleting")
    if row.status != "deleted":
        row.status, row.deleted_at = "deleted", now()
        row.ciphertext = ""  # Retain identity; erase the stored secret.
        await revoke(session, row.id)
    await session.commit()


async def rename(session: AsyncSession, credential_id: str, body: CredentialRename) -> ProviderCredential:
    row = await lookup(session, credential_id, lock=True)
    if row.version != body.expected_version or row.status == "deleted":
        raise HTTPException(409, "Credential changed or deleted; reload before renaming")
    row.name = body.name.strip()
    row.updated_at = now()
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise HTTPException(409, "Credential name is already in use") from error
    return row
