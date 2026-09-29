"""Compatibility imports; one maintained vault implementation."""
from voice_api.services.vault_service import (
    CredentialVault,
    EncryptedSecret,
    SecretScope,
    VaultError,
)

__all__ = ["CredentialVault", "EncryptedSecret", "SecretScope", "VaultError"]
