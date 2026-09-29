"""Encrypt and resolve AI provider credentials within an organization scope."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from voice_api.core.config import Settings
from voice_api.db.tenant_scope import bind_organization
from voice_api.models import LegacyDataTenant, ProviderCredential
from voice_api.services.vault_service import CredentialVault, VaultError

PROVIDER_FIELDS = {
    "groq": "groq_api_key",
    "gemini": "gemini_api_key",
    "sarvam": "sarvam_api_key",
    "cartesia": "cartesia_api_key",
    "jev": "jev_api_key",
}


def encrypt_provider_key(provider: str, plaintext: str) -> tuple[str, str]:
    if provider not in PROVIDER_FIELDS:
        raise ValueError("Unsupported provider")
    encrypted = CredentialVault.from_env().encrypt(plaintext.strip())
    return encrypted.ciphertext, encrypted.key_id


def decrypt_provider_key(provider: str, ciphertext: str, key_id: str) -> str:
    if provider not in PROVIDER_FIELDS:
        raise VaultError("Unsupported provider")
    return CredentialVault.from_env().decrypt(ciphertext, key_id)


async def settings_for_organization(
    session: AsyncSession, organization_id: str, base: Settings
) -> Settings:
    """Return an isolated settings copy; process env credentials are Original-only."""
    bind_organization(session.sync_session, organization_id)
    rows = (await session.scalars(select(ProviderCredential))).all()
    organization_keys = {
        row.provider: decrypt_provider_key(row.provider, row.ciphertext, row.key_id) for row in rows
    }
    is_legacy = (
        await session.scalar(
            select(LegacyDataTenant.organization_id).where(
                LegacyDataTenant.organization_id == organization_id
            )
        )
        is not None
    )
    updates = {
        field: organization_keys.get(provider) or (getattr(base, field) if is_legacy else None)
        for provider, field in PROVIDER_FIELDS.items()
    }
    if not is_legacy:
        updates.update(whatsapp_access_token=None, whatsapp_phone_number_id=None)
    return base.model_copy(update=updates)


async def settings_for_run(run_id: str, base: Settings | None = None) -> Settings:
    """Resolve the owning organization from a persisted run before provider use."""
    from voice_api.core.config import get_settings
    from voice_api.db.session import SessionFactory
    from voice_api.db.tenant_scope import bind_run_organization

    async with SessionFactory() as session:
        organization_id = await bind_run_organization(session, run_id)
        return await settings_for_organization(session, organization_id, base or get_settings())
