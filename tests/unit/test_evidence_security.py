import json
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from voice_api.integrations import vault
from voice_api.integrations.routes import ConnectionBody
from voice_runtime.execution.redaction import redact


def test_redaction_preserves_usage_and_removes_credentials():
    data = {
        "authorization": "Bearer credential-value",
        "nested": [{"access_token": "hidden"}],
        "prompt_tokens": 12,
        "output": "provider echoed credential-value",
    }
    result = redact(data, ["credential-value"])
    assert result["prompt_tokens"] == 12
    assert result["nested"] == [{"access_token": "<redacted>"}]
    assert result["output"] == "provider echoed <redacted>"
    assert data["authorization"] == "Bearer credential-value"


def test_vault_settings_rotation_and_wrong_key(monkeypatch):
    old_key, new_key = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    monkeypatch.setattr(
        vault,
        "get_settings",
        lambda: SimpleNamespace(
            integration_keys=json.dumps({"old": old_key}), integration_active_key="old"
        ),
    )
    encrypted = vault.CredentialVault.from_env().encrypt("test-credential")
    rotating = vault.CredentialVault({"old": old_key, "new": new_key}, "new")
    rotated = rotating.rotate(encrypted.ciphertext, encrypted.key_id)
    assert rotated.key_id == "new"
    assert (
        vault.CredentialVault({"new": new_key}, "new").decrypt(rotated.ciphertext, "new")
        == "test-credential"
    )
    with pytest.raises(vault.VaultError):
        vault.CredentialVault({"old": new_key}, "old").decrypt(encrypted.ciphertext, "old")


def test_connection_config_cannot_accept_secret():
    with pytest.raises(ValueError):
        ConnectionBody(
            label="test",
            provider="whatsapp",
            config={
                "phone_number_id": "123",
                "waba_id": "456",
                "api_version": "v23.0",
                "access_token": "do-not-store-here",
            },
        )
