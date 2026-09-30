"""Encrypt and resolve AI provider credentials within an organization scope."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from voice_api.core.config import Settings
from voice_api.db.tenant_scope import bind_organization
from voice_api.models import ProviderCredential, Run
from voice_api.services.credential_service import credential_scope
from voice_api.services.vault_service import CredentialVault, SecretScope, VaultError

PROVIDER_FIELDS = {
    "groq": "groq_api_key",
    "openrouter": "openrouter_api_key",
    "gemini": "gemini_api_key",
    "sarvam": "sarvam_api_key",
    "cartesia": "cartesia_api_key",
    "jev": "jev_api_key",
}


def encrypt_provider_key(provider: str, plaintext: str, *, scope: SecretScope) -> tuple[str, str]:
    if provider not in PROVIDER_FIELDS:
        raise ValueError("Unsupported provider")
    encrypted = CredentialVault.from_env().encrypt(plaintext.strip(), scope=scope)
    return encrypted.ciphertext, encrypted.key_id


def decrypt_provider_key(provider: str, ciphertext: str, key_id: str, *, scope: SecretScope) -> str:
    if provider not in PROVIDER_FIELDS:
        raise VaultError("Unsupported provider")
    return CredentialVault.from_env().decrypt(ciphertext, key_id, scope=scope)


async def settings_for_organization(
    session: AsyncSession, organization_id: str, base: Settings, *, credential_ids: dict[str, str] | None = None
) -> Settings:
    """Catalog/ingestion compatibility: only an unambiguous stored org key is used."""
    bind_organization(session.sync_session, organization_id)
    rows = (await session.scalars(select(ProviderCredential).where(
        ProviderCredential.status == "stored", ProviderCredential.deleted_at.is_(None)
    ))).all()
    updates = dict.fromkeys(PROVIDER_FIELDS.values())
    for provider, field in PROVIDER_FIELDS.items():
        selected = (credential_ids or {}).get(provider)
        provider_rows = [row for row in rows if row.provider == provider]
        matching = [row for row in provider_rows if row.id == selected] if selected else (
            provider_rows if len(provider_rows) == 1 else [row for row in provider_rows if row.legacy_default]
        )
        if len(matching) == 1:
            row = matching[0]
            try:
                updates[field] = decrypt_provider_key(provider, row.ciphertext, row.key_id, scope=credential_scope(row))
            except VaultError:
                pass  # Catalog availability is safe status; execution fails closed below.
    updates.update(whatsapp_access_token=None, whatsapp_phone_number_id=None, provider_stage_keys={})
    return base.model_copy(update=updates)


async def settings_for_run(run_id: str, base: Settings | None = None) -> Settings:
    """Resolve the owning organization from a persisted run before provider use."""
    from voice_api.core.config import get_settings
    from voice_api.db.session import SessionFactory
    from voice_api.db.tenant_scope import bind_run_organization

    async with SessionFactory() as session:
        organization_id = await bind_run_organization(session, run_id)
        run = await session.get(Run, run_id)
        return await settings_for_snapshot(session, organization_id, run.resolved_config, base or get_settings(), run_id=run_id)


def stage_providers(snapshot: dict) -> dict[str, str]:
    result = {stage: snapshot[stage]["provider"] for stage in ("stt", "llm", "tts") if stage in snapshot}
    classifier = snapshot.get("classifier", {})
    if classifier.get("enabled", True):
        result["classifier"] = "jev" if classifier.get("classifier_type") == "jev" else (classifier.get("llm") or {}).get("provider", "groq")
    summary = snapshot.get("context", {}).get("summarizer", {})
    if summary.get("enabled"):
        result["summarizer"] = (summary.get("model") or {}).get("provider", result.get("llm", "groq"))
    if snapshot.get("knowledge_base_ids"):
        result["embedding"] = "gemini"
    return result


def stage_reference(snapshot: dict, stage: str) -> str | None:
    explicit = snapshot.get("credential_refs", {}).get(stage)
    return explicit or snapshot.get(stage, {}).get("credential_id")


async def resolve_references(session: AsyncSession, snapshot: dict, *, strict: bool = True) -> dict[str, dict]:
    """Map legacy configs without rewriting published JSON; ambiguity is an error."""
    from fastapi import HTTPException

    from voice_api.db.tenant_scope import required_organization

    org_id = required_organization(session.sync_session)
    refs = {}
    for stage, provider in stage_providers(snapshot).items():
        ref = stage_reference(snapshot, stage)
        query = select(ProviderCredential).where(ProviderCredential.org_id == org_id,
            ProviderCredential.provider == provider, ProviderCredential.status == "stored",
            ProviderCredential.deleted_at.is_(None))
        if ref:
            query = query.where(ProviderCredential.id == ref)
        else:
            query = query.where(ProviderCredential.legacy_default.is_(True))
        rows = (await session.scalars(query)).all()
        if len(rows) != 1:
            if not strict and not ref:
                continue
            raise HTTPException(422, f"Select a stored {provider} credential for {stage}")
        row = rows[0]
        refs[stage] = {"credential_id": row.id, "version": row.version, "provider": provider}
    return refs


async def settings_for_snapshot(session: AsyncSession, organization_id: str, snapshot: dict,
                                base: Settings, *, run_id: str) -> Settings:
    from fastapi import HTTPException

    from voice_api.services.credential_lease_service import acquire, admit_settings, issue

    bind_organization(session.sync_session, organization_id)
    admit_settings(base)
    await acquire(session, run_id)
    pinned = snapshot.get("_resolved", {}).get("credentials")
    refs = pinned if pinned is not None else await resolve_references(session, snapshot)
    if set(refs) != set(stage_providers(snapshot)):
        raise HTTPException(422, "Run credential bindings are incomplete")
    updates = dict.fromkeys(PROVIDER_FIELDS.values())
    stage_keys = {}
    for stage, provider in stage_providers(snapshot).items():
        ref = refs[stage]
        row = await session.scalar(select(ProviderCredential).where(
            ProviderCredential.id == ref["credential_id"], ProviderCredential.org_id == organization_id
        ).with_for_update())
        if row is None or row.status != "stored" or row.provider != provider or row.version != ref["version"]:
            raise HTTPException(422, "Run credential was replaced or revoked")
        try:
            key = decrypt_provider_key(provider, row.ciphertext, row.key_id, scope=credential_scope(row))
        except VaultError as error:
            raise HTTPException(503, "Run credential is unavailable") from error
        stage_keys[stage] = key
        updates[PROVIDER_FIELDS[provider]] = key
        await issue(session, run_id, row)
    updates.update(whatsapp_access_token=None, whatsapp_phone_number_id=None, provider_stage_keys=stage_keys)
    await session.commit()
    return base.model_copy(update=updates)
