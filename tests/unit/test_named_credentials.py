"""Offline envelope, stage, write-only schema and bounded lease contracts."""

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from voice_api.schemas.credentials import CredentialCreate
from voice_api.services import credential_lease_service as leases
from voice_api.services.vault_service import CredentialVault, SecretScope, VaultError
from voice_runtime.execution.credential_keys import stage_api_key
from voice_runtime.telephony.twilio import TwilioCredentials


@pytest.fixture
def vault():
    return CredentialVault({"root-a": Fernet.generate_key().decode()}, "root-a")


@pytest.fixture
def scope():
    return SecretScope("org-a", "credential-a", "groq", "api_key", 1)


def test_envelope_has_wrapped_per_secret_key_and_random_nonces(vault, scope):
    first = vault.encrypt("sentinel-provider-key", scope=scope)
    second = vault.encrypt("sentinel-provider-key", scope=scope)
    assert first.ciphertext.startswith("aesgcm:")
    assert first.ciphertext != second.ciphertext
    assert "sentinel-provider-key" not in first.ciphertext
    assert first.key_id == "root-a" != scope.record_id
    assert vault.decrypt(first.ciphertext, first.key_id, scope=scope) == "sentinel-provider-key"


@pytest.mark.parametrize("field,value", [("org_id", "org-b"), ("record_id", "credential-b"),
    ("provider", "gemini"), ("purpose", "auth_token"), ("version", 2)])
def test_envelope_cannot_be_transplanted(vault, scope, field, value):
    encrypted = vault.encrypt("secret", scope=scope)
    with pytest.raises(VaultError, match="could not be decrypted"):
        vault.decrypt(encrypted.ciphertext, encrypted.key_id, scope=replace(scope, **{field: value}))


def test_legacy_dual_read_explicit_rotation_and_root_failure(scope):
    root = Fernet.generate_key()
    old = Fernet(root).encrypt(b"legacy-secret").decode()
    vault = CredentialVault({"old": root.decode(), "new": Fernet.generate_key().decode()}, "new")
    assert vault.decrypt(old, "old", scope=scope) == "legacy-secret"
    upgraded = vault.rotate(old, "old", scope=scope)
    assert upgraded.key_id == "new" and upgraded.ciphertext.startswith("aesgcm:")
    assert vault.decrypt(upgraded.ciphertext, "new", scope=scope) == "legacy-secret"
    with pytest.raises(VaultError):
        vault.decrypt(upgraded.ciphertext, "old", scope=scope)
    with pytest.raises(TypeError):
        vault.encrypt("unscoped")


def test_twilio_rest_key_is_distinct_from_signature_token():
    body = CredentialCreate(name="Sales account", provider="twilio", account_sid="AC" + "a" * 32,
        api_key_sid="SK" + "b" * 32, api_key_secret="rest-secret", auth_token="signature-secret")
    assert "rest-secret" not in repr(body)
    credentials = TwilioCredentials("AC" + "a" * 32, "signature-secret", "SK" + "b" * 32, "rest-secret")
    assert credentials.rest_auth == ("SK" + "b" * 32, "rest-secret")
    assert credentials.auth_token == "signature-secret"
    assert "signature-secret" not in repr(credentials)
    with pytest.raises(ValueError, match="API key"):
        _ = TwilioCredentials("AC" + "a" * 32, "signature-secret").rest_auth


def test_stage_selection_cannot_fall_back_to_environment(monkeypatch):
    monkeypatch.setenv("VOICE_GROQ_API_KEY", "deployment-sentinel")
    settings = SimpleNamespace(groq_api_key="deployment-sentinel", provider_stage_keys={"llm": "agent-key", "classifier": "classifier-key"})
    assert stage_api_key(settings, "llm", "groq") == "agent-key"
    assert stage_api_key(settings, "classifier", "groq") == "classifier-key"
    assert stage_api_key(settings, "summarizer", "groq") is None


def test_hosted_admission_and_phase_limits():
    with pytest.raises(HTTPException) as error:
        leases.admit_settings(SimpleNamespace(env="production", hosted_calls_enabled=False))
    assert error.value.status_code == 503
    assert (leases.HANDSHAKE_SECONDS, leases.CALL_SECONDS, leases.CLEANUP_SECONDS) == (60, 300, 60)
    assert leases.call_seconds(SimpleNamespace(call_max_duration_seconds=300), {"call_limits": {"max_duration_secs": 900}}) == 300


async def test_revocation_cancels_inflight_work(monkeypatch):
    count = 0
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def check(_run):
        nonlocal count
        count += 1
        if count > 1:
            raise leases.CredentialRevoked()

    async def operation():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    monkeypatch.setattr(leases, "check", check)
    with pytest.raises(leases.CredentialRevoked):
        await leases.guard("run", operation, timeout_secs=5)
    assert started.is_set() and cancelled.is_set()


async def test_wrapper_rejects_before_any_provider_work(monkeypatch):
    monkeypatch.setattr(leases, "check", AsyncMock(side_effect=leases.CredentialRevoked()))
    operation = AsyncMock()
    with pytest.raises(leases.CredentialRevoked):
        await leases.guard("run", operation, timeout_secs=1)
    operation.assert_not_awaited()
