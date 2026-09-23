import hashlib
import hmac
import json
from types import SimpleNamespace

from cryptography.fernet import Fernet
from voice_api.integrations import vault
from voice_api.models import (
    Agent,
    AgentVersion,
    IntegrationConnection,
    IntegrationSecret,
    Run,
    ToolInvocation,
)
from voice_api.models.common import new_id


async def test_receipts_are_account_scoped_and_deduplicated(client, database, monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(
        vault,
        "get_settings",
        lambda: SimpleNamespace(
            integration_keys=json.dumps({"test": key}), integration_active_key="test"
        ),
    )
    encryption = vault.CredentialVault({"test": key}, "test")
    secret = encryption.encrypt("test-app-secret")
    connection_ids = [new_id(), new_id()]
    for connection_id in connection_ids:
        database.add(
            IntegrationConnection(
                id=connection_id,
                label=connection_id,
                provider="whatsapp",
                config={"waba_id": "111", "phone_number_id": "222", "api_version": "v23.0"},
            )
        )
    agent = Agent(id=new_id(), name=new_id())
    database.add(agent)
    await database.flush()
    version = AgentVersion(id=new_id(), agent_id=agent.id, version=1, config={})
    database.add(version)
    for connection_id in connection_ids:
        database.add(
            IntegrationSecret(
                id=new_id(),
                connection_id=connection_id,
                name="app_secret",
                ciphertext=secret.ciphertext,
                key_id=secret.key_id,
            )
        )
    await database.flush()
    run = Run(id=new_id(), agent_version_id=version.id, resolved_config={})
    database.add(run)
    await database.flush()
    tools = [
        ToolInvocation(
            id=new_id(),
            run_id=run.id,
            binding_key="send",
            idempotency_key=new_id(),
            connection_id=connection_id,
            provider_message_id="same-external-id",
        )
        for connection_id in connection_ids
    ]
    database.add_all(tools)
    await database.flush()

    async def receipt(account, status, phone_id="222"):
        payload = {
            "entry": [
                {
                    "id": "111",
                    "changes": [
                        {
                            "value": {
                                "metadata": {"phone_number_id": phone_id},
                                "statuses": [
                                    {"id": "same-external-id", "status": status, "timestamp": "1"}
                                ],
                            }
                        }
                    ],
                }
            ]
        }
        body = json.dumps(payload).encode()
        signature = hmac.new(b"test-app-secret", body, hashlib.sha256).hexdigest()
        return await client.post(
            f"/api/integrations/whatsapp/{account}/webhook",
            content=body,
            headers={
                "X-Hub-Signature-256": f"sha256={signature}",
                "Content-Type": "application/json",
            },
        )

    assert (await receipt(connection_ids[0], "delivered")).status_code == 204
    assert (await receipt(connection_ids[0], "delivered")).status_code == 204
    assert (await receipt(connection_ids[0], "read", phone_id="wrong-account")).status_code == 204
    assert len(tools[0].receipts) == 1 and tools[1].receipts == []
    assert (await receipt(connection_ids[1], "sent")).status_code == 204
    assert tools[1].receipts[0]["status"] == "sent"


async def test_invalid_credentials_not_echoed_in_validation(client):
    response = await client.post(
        "/api/integrations",
        json={
            "label": "test",
            "provider": "whatsapp",
            "config": {
                "phone_number_id": "1",
                "waba_id": "2",
                "api_version": "v23.0",
                "access_token": "private-example",
            },
        },
    )
    assert response.status_code == 422
    assert "private-example" not in response.text
