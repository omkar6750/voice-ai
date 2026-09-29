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
    old = vault.CredentialVault({"old": old_key}, "old")
    scope = vault.SecretScope("org", "secret", "twilio", "api_key", 1)
    encrypted = old.encrypt("test-credential", scope=scope)
    rotating = vault.CredentialVault({"old": old_key, "new": new_key}, "new")
    rotated = rotating.rotate(encrypted.ciphertext, encrypted.key_id, scope=scope)
    assert rotated.key_id == "new"
    assert (
        vault.CredentialVault({"new": new_key}, "new").decrypt(rotated.ciphertext, "new", scope=scope)
        == "test-credential"
    )
    with pytest.raises(vault.VaultError):
        vault.CredentialVault({"old": new_key}, "old").decrypt(encrypted.ciphertext, "old", scope=scope)


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
