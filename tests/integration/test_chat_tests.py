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


async def test_ticket_dispatch_compiles_before_claiming(database, version, monkeypatch):
    from types import SimpleNamespace

    from voice_api.services import runtime_dispatch

    row = await chat_service.create(database, CreateChat(agent_version_id=version.id))
    monkeypatch.setattr(
        runtime_dispatch,
        "settings_for_snapshot",
        AsyncMock(return_value=SimpleNamespace(provider_stage_keys={})),
    )
    runtime_control = AsyncMock(side_effect=[{"boot_id": str(uuid4())}, {}])
    monkeypatch.setattr(runtime_dispatch, "control", runtime_control)
    monkeypatch.setattr(
        chat_service, "control", AsyncMock(return_value={"ticket": "test", "ws_url": "ws://test"})
    )
    result = await chat_service.ticket(database, row)
    run = await database.get(Run, result["run_id"])
    assert run.status == "claimed"
    assert "_compiled_flow" in run.resolved_config
    assert runtime_control.await_count == 2


async def test_orphan_preparation_retry_and_in_progress_guard(database, version, monkeypatch):
    from datetime import timedelta

    from voice_api.models.common import now

    row = await chat_service.create(database, CreateChat(agent_version_id=version.id))
    dispatch = AsyncMock(side_effect=HTTPException(503, "Runtime unavailable"))
    monkeypatch.setattr(chat_service, "dispatch", dispatch)
    with pytest.raises(HTTPException):
        await chat_service.ticket(database, row)
    old_run_id = row.active_run_id
    row.status = "connecting"
    await database.commit()
    with pytest.raises(HTTPException, match="still in progress"):
        await chat_service.ticket(database, row)
    assert dispatch.await_count == 1
    row.updated_at = now() - timedelta(minutes=2)
    await database.commit()
    with pytest.raises(HTTPException) as error:
        await chat_service.ticket(database, row)
    assert error.value.status_code == 503
    assert row.active_run_id != old_run_id
    assert dispatch.await_count == 2
    assert row.error["stage"] == "setup"


async def test_database_setup_failure_rolls_back_and_saves_error(database, version, monkeypatch):
    row = await chat_service.create(database, CreateChat(agent_version_id=version.id))

    async def broken_dispatch(session, run, **kwargs):
        run.status = "claimed"
        await session.commit()
        run.config_hash = "broken"
        await session.commit()  # Exercise the real claimed-snapshot database guard.

    monkeypatch.setattr(chat_service, "dispatch", broken_dispatch)
    with pytest.raises(HTTPException) as error:
        await chat_service.ticket(database, row)
    assert error.value.status_code == 503
    await database.refresh(row)
    assert row.status == "failed"
    assert row.error["diagnostic_id"]
    assert (await database.get(Run, row.active_run_id)).status == "failed"


async def test_generated_fact_evidence_and_inspection(database, version):
    import time

    from voice_api.api.v1.endpoints.evidence import store_record
    from voice_api.models import ToolInvocation
    from voice_runtime.contracts.evidence import FlowVisitStarted, ToolStarted

    config = deepcopy(version.config)
    config["fact_slots"] = [
        {
            "key": "caller_name",
            "description": "Caller name",
            "value_type": "string",
            "nodes": ["opening"],
        }
    ]
    version.config = config
    await database.commit()
    row = await chat_service.create(database, CreateChat(agent_version_id=version.id))
    run = Run(
        channel="text_test",
        agent_version_id=version.id,
        status="queued",
        resolved_config=row.snapshot,
        contact_snapshot={},
    )
    database.add(run)
    await database.flush()
    tick = time.time_ns()
    await store_record(
        database,
        run.id,
        FlowVisitStarted(
            id=str(uuid4()),
            run_id=run.id,
            kind="flow_visit_started",
            timestamp_ns=tick,
            visit_id=str(uuid4()),
            span_id=str(uuid4()),
            sequence=1,
            node_key="opening",
            started_ns=tick,
        ),
    )
    invocation_id = str(uuid4())
    record = ToolStarted(
        id=str(uuid4()),
        run_id=run.id,
        kind="tool_started",
        timestamp_ns=tick + 1000,
        invocation_id=invocation_id,
        binding_key="record_caller_name",
        arguments={"value": "Tester"},
        started_ns=tick + 1000,
    )
    for _ in range(2):
        await store_record(database, run.id, record)
    assert (await database.get(ToolInvocation, invocation_id)).arguments == {"value": "Tester"}
    message = ChatMessage(
        conversation_id=row.id,
        run_id=run.id,
        sequence=1,
        kind="evidence",
        payload={"kind": "tool_started", "invocation_id": invocation_id},
    )
    database.add(message)
    await database.flush()
    inspection = await chat.inspect(row.id, message.id, session=database)
    assert inspection["tool"]["binding_key"] == "record_caller_name"
    assert inspection["tool"]["arguments"] == {"value": "Tester"}
    unknown = record.model_copy(
        update={"id": str(uuid4()), "invocation_id": str(uuid4()), "binding_key": "record_unknown"}
    )
    with pytest.raises(HTTPException) as failure:
        await store_record(database, run.id, unknown)
    assert failure.value.status_code == 422
    scoped = deepcopy(run.resolved_config)
    scoped["fact_slots"][0]["nodes"] = ["other_node"]
    run.resolved_config = scoped
    await database.flush()
    with pytest.raises(HTTPException):
        await store_record(
            database,
            run.id,
            record.model_copy(update={"id": str(uuid4()), "invocation_id": str(uuid4())}),
        )


async def test_browser_ticket_dispatch_compiles_before_claiming(database, version, monkeypatch):
    from types import SimpleNamespace

    from voice_api.services import remote_browser_service, runtime_dispatch

    run, browser = await remote_browser_service.create_browser_session(
        database, agent_version_id=version.id
    )
    assert run.status == "queued"
    monkeypatch.setattr(
        runtime_dispatch,
        "settings_for_snapshot",
        AsyncMock(return_value=SimpleNamespace(provider_stage_keys={})),
    )
    runtime_control = AsyncMock(side_effect=[{"boot_id": str(uuid4())}, {}])
    monkeypatch.setattr(runtime_dispatch, "control", runtime_control)
    ticket_control = AsyncMock(return_value={"ticket": "test", "ws_url": "ws://test"})
    monkeypatch.setattr(remote_browser_service, "control", ticket_control)

    result = await remote_browser_service.issue_browser_ticket(
        browser.id, database, actor_user_id="test-operator"
    )
    await database.refresh(run)
    assert result["ticket"] == "test"
    assert run.status == "claimed"
    assert "_compiled_flow" in run.resolved_config
    assert runtime_control.await_count == 2
    ticket_control.assert_awaited_once()


@pytest.mark.parametrize("provider", ["sim7600", "twilio"])
async def test_phone_dispatch_compiles_before_claiming(database, version, monkeypatch, provider):
    from types import SimpleNamespace

    from voice_api.models import IntegrationConnection, RuntimeEndpoint
    from voice_api.models.common import now
    from voice_api.schemas.call import TelephonySelection
    from voice_api.services import (
        call_service,
        remote_twilio_dispatch,
        runtime_dispatch,
        twilio_service,
    )
    from voice_runtime.telephony.twilio import TwilioCredentials

    version.status = "published"
    version.published_at = now()
    contact = Contact(name="Dispatch test", phone_number="+12025550123", timezone="UTC")
    endpoint = RuntimeEndpoint(
        name="dispatch-" + str(uuid4()), config={"at_port": "COM3", "audio_port": "COM4"}
    )
    database.add_all([contact, endpoint])
    await database.flush()
    selection = TelephonySelection(provider=provider, endpoint_id=endpoint.id)
    if provider == "twilio":
        connection = IntegrationConnection(
            label="dispatch-" + str(uuid4()),
            provider="twilio_voice",
            enabled=True,
            config={"phone_numbers": [{"phone_number": "+12025550124", "voice": True}]},
        )
        database.add(connection)
        await database.flush()
        selection = TelephonySelection(
            provider="twilio", connection_id=connection.id, from_number="+12025550124"
        )
        monkeypatch.setattr(
            twilio_service,
            "resolve_twilio_credentials",
            AsyncMock(
                return_value=(
                    connection,
                    TwilioCredentials(
                        account_sid="test-account",
                        auth_token="test-token",
                        api_key_sid="test-key",
                        api_key_secret="test-secret",
                    ),
                )
            ),
        )
    run, call = await call_service.queue_call(database, contact.id, version.id, telephony=selection)
    await database.commit()
    assert run.status == call.status == "queued"

    async def credentials(session, *_args, **_kwargs):
        # Real credential resolution queries and commits before runtime preparation.
        await session.flush()
        await session.commit()
        return SimpleNamespace(provider_stage_keys={})

    monkeypatch.setattr(runtime_dispatch, "settings_for_snapshot", credentials)
    prepared_bodies = []

    async def control(path, body):
        await database.refresh(run)
        if path == "/v1/sessions":
            assert run.status == "queued"
            assert "_compiled_flow" in run.resolved_config
            assert body["channel"] == provider
            assert body["destination"] == contact.phone_number
            prepared_bodies.append(dict(body))
            return {"boot_id": str(uuid4())}
        assert path == "/v1/sessions/start"
        assert run.status == "claimed"
        return {}

    runtime_control = AsyncMock(side_effect=control)
    monkeypatch.setattr(runtime_dispatch, "control", runtime_control)
    if provider == "twilio":
        settings = SimpleNamespace(
            public_base_url="https://api.example.test",
            runtime_public_base_url="https://runtime.example.test",
            runtime_control_token="test",
            runtime_service_token="test",
        )
        await remote_twilio_dispatch.dispatch_twilio_call(database, call, run, settings)
    else:
        await runtime_dispatch.dispatch(database, run)
    await database.refresh(run)
    assert run.status == "claimed"
    assert call.status == "dialing"
    if provider == "sim7600":
        assert run.resolved_config["_resolved"]["endpoint"]["at_port"] == "COM3"
    else:
        assert prepared_bodies[0]["from_number"] == "+12025550124"
    # An existing assignment is reused without recompilation or a second dial.
    await runtime_dispatch.dispatch(database, run)
    assert runtime_control.await_count == 2


@pytest.mark.parametrize("channel", ["phone", "browser", "text_test"])
async def test_dispatch_rejects_frozen_unassigned_run(database, version, monkeypatch, channel):
    from voice_api.services import runtime_dispatch

    run = Run(
        channel=channel,
        status="claimed",
        agent_version_id=version.id,
        resolved_config={"name": "Frozen"},
        config_hash="frozen",
    )
    database.add(run)
    await database.commit()
    control = AsyncMock()
    credentials = AsyncMock()
    monkeypatch.setattr(runtime_dispatch, "control", control)
    monkeypatch.setattr(runtime_dispatch, "settings_for_snapshot", credentials)
    with pytest.raises(HTTPException) as failure:
        await runtime_dispatch.dispatch(database, run)
    assert failure.value.status_code == 409
    assert "frozen snapshot" in failure.value.detail
    assert run.resolved_config == {"name": "Frozen"}
    control.assert_not_awaited()
    credentials.assert_not_awaited()
