"""AES-GCM envelopes with scoped AAD and legacy Fernet reads."""

import base64
import json
import os
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from voice_api.core.config import get_settings


class VaultError(ValueError):
    pass


@dataclass(frozen=True)
class SecretScope:
    org_id: str
    record_id: str
    provider: str
    purpose: str
    version: int = 1

    def aad(self) -> bytes:
        if not all((self.org_id, self.record_id, self.provider, self.purpose)) or self.version < 1:
            raise VaultError("Credential scope is incomplete")
        return json.dumps(self.__dict__, sort_keys=True, separators=(",", ":")).encode()


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii")


def _decode(value: str) -> bytes:
    return base64.b64decode(value, altchars=b"-_", validate=True)


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
            self._raw = {name: _decode(value) for name, value in keys.items()}
            if any(len(value) != 32 for value in self._raw.values()):
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

    def encrypt(self, plaintext: str, *, scope: SecretScope) -> EncryptedSecret:
        if not isinstance(plaintext, str) or not plaintext:
            raise VaultError("Credential must not be empty")
        aad = scope.aad()
        dek = AESGCM.generate_key(bit_length=256)
        nonce, wrap_nonce = os.urandom(12), os.urandom(12)
        payload = {
            "v": 1,
            "nonce": _encode(nonce),
            "data": _encode(AESGCM(dek).encrypt(nonce, plaintext.encode(), aad)),
            "wrap_nonce": _encode(wrap_nonce),
            "wrapped_key": _encode(AESGCM(self._raw[self.active_key]).encrypt(
                wrap_nonce, dek, aad + b"/dek/" + self.active_key.encode()
            )),
        }
        return EncryptedSecret("aesgcm:" + json.dumps(payload, separators=(",", ":")), self.active_key)

    def decrypt(self, ciphertext: str, key_id: str, *, scope: SecretScope) -> str:
        try:
            aad = scope.aad()
            if not ciphertext.startswith("aesgcm:"):
                # Legacy data has no AAD; callers establish ownership before dual reads.
                return self._keys[key_id].decrypt(ciphertext.encode("ascii")).decode("utf-8")
            payload = json.loads(ciphertext[7:])
            if payload["v"] != 1:
                raise ValueError
            dek = AESGCM(self._raw[key_id]).decrypt(
                _decode(payload["wrap_nonce"]), _decode(payload["wrapped_key"]),
                aad + b"/dek/" + key_id.encode(),
            )
            return AESGCM(dek).decrypt(_decode(payload["nonce"]), _decode(payload["data"]), aad).decode("utf-8")
        except (KeyError, InvalidToken, InvalidTag, ValueError, TypeError, UnicodeError, AttributeError):
            raise VaultError("Credential could not be decrypted") from None

    def rotate(self, ciphertext: str, key_id: str, *, scope: SecretScope) -> EncryptedSecret:
        return self.encrypt(self.decrypt(ciphertext, key_id, scope=scope), scope=scope)
