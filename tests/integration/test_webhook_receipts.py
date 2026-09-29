import hashlib
import hmac
import json
from types import SimpleNamespace

from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncSession
from voice_api.db.session import get_session
from voice_api.main import app
from voice_api.models import (
    Agent,
    AgentVersion,
    IntegrationConnection,
    IntegrationSecret,
    Run,
    ToolInvocation,
)
from voice_api.models.common import new_id
from voice_api.services import vault_service
from voice_api.services.vault_service import CredentialVault, SecretScope


async def test_receipts_are_account_scoped_and_deduplicated(client, database, monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(
        vault_service,
        "get_settings",
        lambda: SimpleNamespace(
            integration_keys=json.dumps({"test": key}), integration_active_key="test"
        ),
    )
    encryption = CredentialVault({"test": key}, "test")
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
        secret_id = new_id()
        secret = encryption.encrypt("test-app-secret", scope=SecretScope(
            database.sync_session.info["organization_scope_id"], secret_id,
            "whatsapp", "app_secret", 1,
        ))
        database.add(
            IntegrationSecret(
                id=secret_id,
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

    async def receipt(account, status, phone_id="222", timestamp="1"):
        payload = {
            "entry": [
                {
                    "id": "111",
                    "changes": [
                        {
                            "value": {
                                "metadata": {"phone_number_id": phone_id},
                                "statuses": [
                                    {
                                        "id": "same-external-id",
                                        "status": status,
                                        "timestamp": timestamp,
                                        **(
                                            {"errors": [{"code": 131026, "title": "Undeliverable"}]}
                                            if status == "failed"
                                            else {}
                                        ),
                                    }
                                ],
                            }
                        }
                    ],
                }
            ]
        }
        body = json.dumps(payload).encode()
        signature = hmac.new(b"test-app-secret", body, hashlib.sha256).hexdigest()
        previous = app.dependency_overrides[get_session]

        async def unscoped_session():
            connection = await database.connection()
            async with AsyncSession(
                bind=connection,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            ) as session:
                yield session

        app.dependency_overrides[get_session] = unscoped_session
        try:
            return await client.post(
                f"/api/integrations/whatsapp/{account}/webhook",
                content=body,
                headers={
                    "X-Hub-Signature-256": f"sha256={signature}",
                    "Content-Type": "application/json",
                },
            )
        finally:
            app.dependency_overrides[get_session] = previous

    first_receipt = await receipt(connection_ids[0], "delivered")
    assert first_receipt.status_code == 204, first_receipt.text
    assert (await receipt(connection_ids[0], "delivered")).status_code == 204
    assert (await receipt(connection_ids[0], "read", phone_id="wrong-account")).status_code == 204
    await database.refresh(tools[0])
    await database.refresh(tools[1])
    assert len(tools[0].receipts) == 1 and tools[1].receipts == []
    assert (await receipt(connection_ids[1], "sent")).status_code == 204
    await database.refresh(tools[1])
    assert tools[1].receipts[0]["status"] == "sent"
    assert (await receipt(connection_ids[1], "failed", timestamp="2")).status_code == 204
    await database.refresh(tools[1])

    timeline = await client.get(f"/api/v1/runs/{run.id}/timeline")
    assert timeline.status_code == 200
    whatsapp_tool = next(item for item in timeline.json()["tools"] if item["id"] == tools[1].id)
    assert [item["status"] for item in whatsapp_tool["receipts"]] == ["sent", "failed"]
    assert whatsapp_tool["receipts"][1]["errors"][0]["title"] == "Undeliverable"
    receipt_events = [
        event
        for event in timeline.json()["context_events"]
        if event["tool_invocation_id"] == tools[1].id
    ]
    assert [event["payload"]["status"] for event in receipt_events] == ["sent", "failed"]
    assert all(event["source"] == "whatsapp_receipt" for event in receipt_events)
    assert all(event["status"] == "pending" for event in receipt_events)
    assert receipt_events[0]["occurred_at"] < receipt_events[1]["occurred_at"]


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
