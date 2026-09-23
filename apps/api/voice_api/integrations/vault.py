"""Authenticated, key-addressed credential encryption. No development fallback keys."""

import json
from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken

from voice_api.config import get_settings


class VaultError(ValueError):
    pass


@dataclass(frozen=True)
class EncryptedSecret:
    ciphertext: str
    key_id: str


class CredentialVault:
    def __init__(self, keys: dict[str, str], active_key: str):
        try:
            if not keys or not active_key or active_key not in keys:
                raise ValueError
            if any(
                not isinstance(k, str) or not k or not isinstance(v, str) for k, v in keys.items()
            ):
                raise ValueError
            self._keys = {name: Fernet(value.encode("ascii")) for name, value in keys.items()}
        except (ValueError, TypeError, AttributeError, UnicodeError):
            raise VaultError("Integration encryption is not configured correctly") from None
        self.active_key = active_key

    @classmethod
    def from_env(cls) -> "CredentialVault":
        try:
            settings = get_settings()
            keys = json.loads(settings.integration_keys or "{}")
            active = settings.integration_active_key
            if not isinstance(keys, dict):
                raise ValueError
        except (KeyError, ValueError):
            raise VaultError("Integration encryption is not configured correctly") from None
        return cls(keys, active)

    def encrypt(self, plaintext: str) -> EncryptedSecret:
        if not isinstance(plaintext, str) or not plaintext:
            raise VaultError("Credential must not be empty")
        return EncryptedSecret(
            self._keys[self.active_key].encrypt(plaintext.encode()).decode(), self.active_key
        )

    def decrypt(self, ciphertext: str, key_id: str) -> str:
        try:
            return self._keys[key_id].decrypt(ciphertext.encode("ascii")).decode("utf-8")
        except (KeyError, InvalidToken, ValueError, UnicodeError, AttributeError):
            raise VaultError("Credential could not be decrypted") from None

    def rotate(self, ciphertext: str, key_id: str) -> EncryptedSecret:
        return self.encrypt(self.decrypt(ciphertext, key_id))
