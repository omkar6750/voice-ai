"""Rollback-only chat persistence and tenant-bound API tests."""

from copy import deepcopy
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from voice_api.api.v1.endpoints import chat
from voice_api.models import (
    Agent,
    AgentVersion,
    ChatConversation,
    ChatExecution,
    ChatMessage,
    Contact,
    Run,
)
from voice_api.schemas.chat import CreateChat
from voice_api.services import chat_service
from voice_runtime.contracts import AgentConfig


@pytest.fixture
async def version(database):
    agent = Agent(name="chat-test-" + str(uuid4()))
    database.add(agent)
    await database.flush()
    config = AgentConfig.model_validate(
        {
            "name": "Chat test",
            "classifier": {"enabled": False},
            "flow": {"initial_node": "opening", "nodes": [{"id": "opening", "terminal": True}]},
        }
    ).model_dump(mode="json")
    version = AgentVersion(agent_id=agent.id, version=1, revision=1, status="draft", config=config)
    database.add(version)
    await database.commit()
    return version


async def test_frozen_draft_contact_override_and_text_credentials(database, version):
    contact = Contact(name="Tester", phone_number="+919876543210", timezone="Asia/Calcutta")
    database.add(contact)
    await database.commit()
    row = await chat_service.create(
        database,
        CreateChat(
            agent_version_id=version.id, contact_id=contact.id, whatsapp_number="+919876543211"
        ),
    )
    assert row.contact_snapshot["phone_number"] == "+919876543211"
    assert "stt" not in row.snapshot["_resolved"]["credentials"]
    assert "tts" not in row.snapshot["_resolved"]["credentials"]
    config = deepcopy(version.config)
    config["flow"]["nodes"][0]["role_message"] = "New instruction"
    version.config = config
    version.revision += 1
    await database.commit()
    await database.refresh(row)
    assert row.revision == 1
    assert row.snapshot["flow"]["nodes"][0].get("role_message") != "New instruction"


async def test_commit_ack_replay_and_hidden_voice_runs(database, version):
    row = await chat_service.create(database, CreateChat(agent_version_id=version.id))
    run = Run(
        channel="text_test",
        agent_version_id=version.id,
        status="claimed",
        resolved_config=row.snapshot,
        contact_snapshot={},
    )
    database.add(run)
    await database.flush()
    row.active_run_id = run.id
    database.add(ChatExecution(conversation_id=row.id, run_id=run.id))
    await database.commit()
    record = {
        "id": str(uuid4()),
        "sequence": 1,
        "kind": "assistant",
        "payload": {"text": "Hello", "status": "completed", "api_key": "secret"},
    }
    for _ in range(2):
        assert (
            await chat_service.persist_batch(
                database, run, [record], {"safe": True, "messages": []}, {"chat_state": "connected"}
            )
            == 1
        )
        await database.commit()
    assert (
        await database.scalar(
            select(func.count(ChatMessage.id)).where(ChatMessage.run_id == run.id)
        )
        == 1
    )
    message = await database.get(ChatMessage, record["id"])
    assert message.payload["api_key"] == "<redacted>"
    assert (
        run.id
        not in (await database.scalars(select(Run.id).where(Run.channel != "text_test"))).all()
    )
    detail = await chat.detail(row.id, session=database, actor=None)
    assert detail["messages"][0]["payload"]["text"] == "Hello"
    with pytest.raises(HTTPException) as failure:
        await chat.inspect(str(uuid4()), record["id"], session=database, actor=None)
    assert failure.value.status_code == 404


async def test_setup_failure_persisted_and_uncertain_resume_rejected(
    database, version, monkeypatch
):
    row = await chat_service.create(database, CreateChat(agent_version_id=version.id))
    monkeypatch.setattr(
        chat_service, "dispatch", AsyncMock(side_effect=HTTPException(409, "Runtime busy"))
    )
    with pytest.raises(HTTPException) as failure:
        await chat_service.ticket(database, row)
    assert failure.value.detail["diagnostic_id"] and row.status == "failed"
    row.checkpoint = {"safe": False, "messages": []}
    await database.commit()
    with pytest.raises(HTTPException, match="unresolved"):
        await chat_service.ticket(database, row)


async def test_invalid_node_rejected_without_execution(database, version):
    with pytest.raises(HTTPException) as failure:
        await chat_service.create(
            database, CreateChat(agent_version_id=version.id, starting_node="missing")
        )
    assert failure.value.status_code == 422
    assert not (
        await database.scalars(
            select(ChatConversation).where(ChatConversation.agent_version_id == version.id)
        )
    ).all()
