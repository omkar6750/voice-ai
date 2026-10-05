"""Exercise real Pipecat text processing without paid providers or speech."""

import asyncio
import json
import time
from copy import deepcopy
from uuid import uuid4

import httpx
import pytest
from pipecat.frames.frames import LLMTextFrame
from pipecat.services.openai.llm import OpenAILLMService
from voice_api.schemas.chat import CreateChat
from voice_api.services.provider_credentials import stage_providers
from voice_runner.main import Manager
from voice_runner.settings import RuntimeSettings
from voice_runner.text import run_text
from voice_runtime.contracts import AgentConfig
from voice_shared.contracts import PrepareSession, configuration_hash


class FakeLLM(OpenAILLMService):
    def __init__(self):
        super().__init__(api_key="fake-provider-key", model="fake-model")
        self.inputs = []

    async def _process_context(self, context):
        self.inputs.append(deepcopy(context.get_messages()))
        await self.push_frame(LLMTextFrame("Hello "))
        await asyncio.sleep(0.15)
        await self.push_frame(LLMTextFrame("there."))


def snapshot():
    value = AgentConfig.model_validate(
        {
            "name": "Text test",
            "system_prompt": "",
            "classifier": {"enabled": False},
            "flow": {
                "initial_node": "opening",
                "nodes": [
                    {
                        "id": "opening",
                        "role_message": "Be helpful.",
                        "task_messages": [
                            {
                                "role": "user",
                                "content": "Begin using the configured greeting, then wait.",
                            }
                        ],
                        "transitions": ["closing"],
                    },
                    {"id": "closing", "role_message": "Say goodbye.", "terminal": True},
                ],
            },
        }
    ).model_dump(mode="json")
    value["llm"]["fallback"] = None
    value["_resolved"] = {"tools": {}, "pipeline_logs_enabled": False, "contact": {}}
    value["_text_test"] = True
    return value


@pytest.fixture
async def text_session(tmp_path, monkeypatch):
    from voice_runtime.execution import native_host

    def forbidden(*args, **kwargs):
        raise AssertionError("Speech, VAD and capture must never be constructed")

    for name in ("build_speech_services", "SileroVADAnalyzer", "CallCapture"):
        monkeypatch.setattr(native_host, name, forbidden)
    llms = []

    def build(*args, **kwargs):
        llm = FakeLLM()
        llms.append(llm)
        return llm

    monkeypatch.setattr(native_host, "build_llm_service", build)
    settings = RuntimeSettings(
        _env_file=None,
        runtime_spool_dir=str(tmp_path / "spool"),
        recordings_dir=str(tmp_path / "recordings"),
        runtime_service_token="service-secret",
        runtime_control_token="control-secret",
    )
    manager = Manager(settings)
    await manager.control_client.aclose()
    captured = []

    async def backend(request):
        body = json.loads(request.content)
        captured.append(body)
        return httpx.Response(
            200,
            json={
                "accepted": len(body.get("records", [])),
                "text_accepted": len(body.get("text_records", [])),
                "renewed": True,
                "context_events": [],
            },
        )

    manager.control_client = httpx.AsyncClient(
        transport=httpx.MockTransport(backend), base_url=settings.api_base_url
    )
    config = snapshot()
    body = PrepareSession(
        run_id=uuid4(),
        organization_id=uuid4(),
        generation=uuid4(),
        grant="session-secret",
        expires_at=time.time() + 900,
        channel="text_test",
        conversation_id=uuid4(),
        config_hash=configuration_hash(config),
        snapshot=config,
        credentials={"llm": "fake-provider-key"},
    )
    session = await manager.prepare(body)
    await manager.start(session)
    try:
        yield session, manager, llms, captured
    finally:
        await manager.close()


async def wait_for(predicate):
    async with asyncio.timeout(8):
        while not predicate():  # noqa: ASYNC110 - observe asynchronous pipeline state in tests
            await asyncio.sleep(0.02)


async def test_text_pipeline_stream_context_and_checkpoint_without_speech(text_session):
    session, _, llms, captured = text_session
    session.task = asyncio.create_task(run_text(session))
    await wait_for(lambda: session.text.checkpoint and session.text.checkpoint.get("safe"))
    assert session.host.capture is None
    assert session.host.worker._idle_timeout_secs is None
    assert any(
        message.get("role") == "user"
        and message.get("content") == "Begin using the configured greeting, then wait."
        for message in llms[0].inputs[0]
    )
    assert any(m.get("content") == "Hello there." for m in session.text.checkpoint["messages"])
    assert any(e["type"] == "delta" for e in session.text.replay)
    await session.text.command(
        {"type": "user_message", "id": str(uuid4()), "text": "What do you offer?"}
    )
    await wait_for(lambda: len(llms[0].inputs) >= 2 and session.text.active is None)
    assert any(m.get("content") == "What do you offer?" for m in llms[0].inputs[-1])
    await session.sync()
    assert session.text.checkpoint["safe"]
    assert any(
        body.get("text_checkpoint", {}).get("safe")
        for body in captured
        if body.get("text_checkpoint")
    )
    await session.text.command({"type": "end", "id": str(uuid4())})
    await wait_for(session.closed.is_set)


async def test_interrupt_partial_and_deduplicate_commands(text_session):
    session, _, llms, _ = text_session
    session.task = asyncio.create_task(run_text(session))
    await wait_for(lambda: session.text.active and session.text.active["text"])
    command = {"type": "user_message", "id": str(uuid4()), "text": "Wait, I have a question."}
    await session.text.command(command)
    await session.text.command(command)
    await wait_for(lambda: len(llms[0].inputs) >= 2 and session.text.active is None)
    messages = [e for e in session.text.replay if e["type"] == "message"]
    assert len([m for m in messages if m["kind"] == "user"]) == 1
    assert any(
        m["kind"] == "assistant"
        and m["payload"]["status"] == "interrupted"
        and m["payload"]["text"] == "Hello "
        for m in messages
    )
    assert any(str(m.get("content", "")).strip() == "Hello" for m in llms[0].inputs[-1])


async def test_provider_failure_preserves_partial_and_redacts(text_session):
    session, _, _, _ = text_session
    session.text.start()
    session.text.delta("partial fake-provider-key")
    await session.text.failure("provider", "Provider failed", "diagnostic-123")
    assistant = next(r for r in session.text.replay if r.get("kind") == "assistant")
    assert assistant["payload"]["status"] == "failed"
    assert "fake-provider-key" not in json.dumps(list(session.text.replay))
    assert any(
        e.get("payload", {}).get("diagnostic_id") == "diagnostic-123" for e in session.text.replay
    )


async def test_uncertain_write_invalidates_safe_checkpoint(text_session):
    session, _, _, _ = text_session
    session.text.checkpoint = {"safe": True, "messages": []}
    session.text.evidence({"kind": "tool_result", "payload": {"status": "uncertain"}})
    await asyncio.gather(*tuple(session.text.pending_tasks))
    assert session.text.uncertain and not session.text.checkpoint["safe"]


async def test_resume_does_not_regenerate_or_replay(text_session):
    session, _, llms, _ = text_session
    session.request.checkpoint = {
        "safe": True,
        "node": "opening",
        "state": {},
        "messages": [
            {"role": "system", "content": "Saved instruction"},
            {"role": "user", "content": "Previous question"},
            {"role": "assistant", "content": "Previous answer"},
        ],
        "dialogue": [
            {"role": "user", "text": "Full caller history before a context reset"},
            {"role": "assistant", "text": "Full agent reply before a context reset"},
        ],
        "command_ids": ["already-sent"],
    }
    session.task = asyncio.create_task(run_text(session))
    await session.text.ready.wait()
    await asyncio.sleep(0.2)
    assert not llms[0].inputs
    assert session.host.context.get_messages()[-1]["content"] == "Previous answer"
    assert session.host.tracker.plain_transcript() == (
        "Caller: Full caller history before a context reset\n"
        "Agent: Full agent reply before a context reset"
    )
    await session.text.command({"type": "user_message", "id": "already-sent", "text": "Duplicate"})
    assert not llms[0].inputs
    await session.text.command({"type": "user_message", "id": str(uuid4()), "text": "Continue"})
    await wait_for(lambda: len(llms[0].inputs) == 1)
    assert any(m.get("content") == "Previous answer" for m in llms[0].inputs[0])


def test_only_text_credential_stages_and_number_validation():
    assert set(stage_providers(snapshot())) == {"llm"}
    with pytest.raises(ValueError):
        CreateChat(agent_version_id=uuid4(), whatsapp_number="invalid")


def test_runtime_text_websocket_single_use_ticket(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from voice_runner import main
    from voice_runtime.execution import native_host

    settings = RuntimeSettings(
        _env_file=None,
        runtime_spool_dir=str(tmp_path / "ws-spool"),
        recordings_dir=str(tmp_path / "ws-recordings"),
        runtime_control_token="control-secret",
        runtime_service_token="service-secret",
        runtime_allowed_origins="http://localhost:5174",
    )
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    monkeypatch.setattr(native_host, "build_llm_service", lambda *args, **kwargs: FakeLLM())

    async def backend(request):
        body = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "accepted": len(body.get("records", [])),
                "text_accepted": len(body.get("text_records", [])),
                "renewed": True,
                "context_events": [],
            },
        )

    with TestClient(main.app) as client:
        manager = main.app.state.manager
        client.portal.call(manager.control_client.aclose)
        manager.control_client = httpx.AsyncClient(
            transport=httpx.MockTransport(backend), base_url=settings.api_base_url
        )
        config = snapshot()
        body = dict(
            run_id=str(uuid4()),
            organization_id=str(uuid4()),
            generation=str(uuid4()),
            grant="session-secret",
            expires_at=time.time() + 900,
            channel="text_test",
            conversation_id=str(uuid4()),
            snapshot=config,
            config_hash=configuration_hash(config),
            credentials={"llm": "fake-provider-key"},
        )
        headers = {"X-Voice-Runtime-Control-Token": "control-secret"}
        prepared = client.post("/v1/sessions", json=body, headers=headers)
        assert prepared.status_code == 200
        identity = {
            "run_id": body["run_id"],
            "generation": body["generation"],
            "boot_id": prepared.json()["boot_id"],
        }
        assert client.post("/v1/sessions/start", json=identity, headers=headers).status_code == 200
        ticket = client.post("/v1/sessions/text-ticket", json=identity, headers=headers)
        assert ticket.status_code == 200
        path = "/v1/text/" + body["run_id"] + "?ticket=" + ticket.json()["ticket"]
        with client.websocket_connect(path, headers={"origin": "http://localhost:5174"}) as ws:
            events = []
            while not any(
                e.get("type") == "message" and e.get("kind") == "assistant" for e in events
            ):
                events.append(ws.receive_json())
            ws.send_json({"type": "user_message", "id": str(uuid4()), "text": "Testing text"})
            while not any(e.get("type") == "message" and e.get("kind") == "user" for e in events):
                events.append(ws.receive_json())
            assert "fake-provider-key" not in json.dumps(events)
            assert (
                client.post("/v1/sessions/text-ticket", json=identity, headers=headers).status_code
                == 409
            )
        from starlette.websockets import WebSocketDisconnect

        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(path, headers={"origin": "http://localhost:5174"}):
                pass


async def test_setup_validation_failure_is_visible_without_sensitive_exception(text_session):
    from voice_shared.compiler import compile_flow_json

    session, _, _, _ = text_session
    compiled = compile_flow_json(session.request.snapshot)
    compiled["initial_node"] = "missing_node"
    session.request.snapshot["_compiled_flow"] = compiled
    session.task = asyncio.create_task(run_text(session))
    await wait_for(session.closed.is_set)
    failures = [e for e in session.text.replay if e["type"] == "error"]
    assert failures
    assert failures[-1]["stage"] == "configuration"
    assert "runtime validation" in failures[-1]["message"]
    assert failures[-1]["diagnostic_id"]
    assert "fake-provider-key" not in json.dumps(failures)


async def test_provider_error_frame_is_persisted_once():
    from types import SimpleNamespace
    from unittest.mock import Mock

    from pipecat.frames.frames import ErrorFrame
    from voice_runtime.execution.observer import EvidenceObserver

    llm, tracker = object(), Mock()
    observer = EvidenceObserver(
        tracker, llm=llm, stt=None, tts=None, llm_model="test", stt_model="", tts_model=""
    )
    frame = ErrorFrame(error="Provider request failed")
    data = SimpleNamespace(frame=frame, source=object())
    for _ in range(4):
        await observer.on_push_frame(data)
    assert tracker.diagnostic.call_count == 1


async def test_generic_pipeline_failure_does_not_repeat_provider_error(text_session):
    session, _, _, _ = text_session
    await session.text.failure("provider", "Provider rejected context", "diagnostic-primary")
    await session.text.failure("runtime", "Pipecat pipeline failed", "diagnostic-secondary")
    failures = [event for event in session.text.replay if event["type"] == "error"]
    assert len(failures) == 1
    assert failures[0]["diagnostic_id"] == "diagnostic-primary"


async def test_completed_turn_does_not_create_interruption(text_session):
    session, _, llms, _ = text_session
    session.task = asyncio.create_task(run_text(session))
    await wait_for(lambda: session.text.checkpoint and session.text.active is None)
    before = len(
        [r for r in session.text.records if r.get("payload", {}).get("kind") == "interruption"]
    )
    await session.text.command(
        {"type": "user_message", "id": str(uuid4()), "text": "A normal next turn"}
    )
    await wait_for(lambda: len(llms[0].inputs) >= 2 and session.text.active is None)
    after = len(
        [r for r in session.text.records if r.get("payload", {}).get("kind") == "interruption"]
    )
    assert after == before
