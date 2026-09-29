from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from voice_api.services.vault_service import CredentialVault
from voice_runtime.execution.native import NativePipelineHost


class _FakeSession:
    def __init__(self, connection, secret):
        self.connection = connection
        self.secret = secret

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def scalars(self, _query):
        return SimpleNamespace(all=lambda: [self.connection])

    async def scalar(self, _query):
        return self.secret


@pytest.mark.asyncio
async def test_pinned_runtime_config_uses_connection_secret_without_global_settings(
    monkeypatch,
) -> None:
    import voice_api.db.session
    import voice_api.db.tenant_scope

    bind = AsyncMock()
    monkeypatch.setattr(voice_api.db.tenant_scope, "bind_run_organization", bind)

    connection = SimpleNamespace(
        id="connection-1",
        config={"phone_number_id": "123456", "api_version": "v23.0"},
    )
    secret = SimpleNamespace(ciphertext="ciphertext", key_id="key-1")
    monkeypatch.setattr(
        voice_api.db.session,
        "SessionFactory",
        lambda: _FakeSession(connection, secret),
    )

    class _Vault:
        def decrypt(self, ciphertext, key_id):
            assert (ciphertext, key_id) == ("ciphertext", "key-1")
            return "connection-token"

    monkeypatch.setattr(CredentialVault, "from_env", classmethod(lambda _cls: _Vault()))
    monkeypatch.delenv("VOICE_WHATSAPP_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("VOICE_WHATSAPP_PHONE_NUMBER_ID", raising=False)

    host = object.__new__(NativePipelineHost)
    host.run_id = "run-1"
    host.settings = SimpleNamespace(
        whatsapp_access_token=None,
        whatsapp_phone_number_id=None,
    )
    resolved = await host._whatsapp_runtime_config(connection_id="connection-1")
    bind.assert_awaited_once()
    assert bind.await_args.args[1] == "run-1"
    assert resolved == (
        "connection-token",
        "123456",
        "connection-1",
        "v23.0",
    )
