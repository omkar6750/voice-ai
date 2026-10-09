"""Service separation contracts without hardware or live provider requests."""

import asyncio
import json
import time
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException
from voice_runner.main import Manager
from voice_runner.settings import RuntimeSettings
from voice_shared.contracts import PrepareSession, configuration_hash
from voice_shared.logging import HttpLoggingMiddleware, body_preview


@pytest.fixture
def settings(tmp_path):
    return RuntimeSettings(
        _env_file=None,
        env="dev",
        runtime_control_token="control-secret",
        runtime_service_token="service-secret",
        runtime_spool_dir=str(tmp_path / "spool"),
        recordings_dir=str(tmp_path / "recordings"),
    )


def prepared(channel="browser", snapshot=None):
    snapshot = snapshot or {"flow": {"nodes": []}, "call_limits": {"max_duration_secs": 600}}
    return PrepareSession(
        run_id=uuid4(),
        organization_id=uuid4(),
        generation=uuid4(),
        grant="session-secret",
        expires_at=time.time() + 900,
        channel=channel,
        snapshot=snapshot,
        config_hash=configuration_hash(snapshot),
        credentials={"llm": "provider-secret"},
    )


async def mock_backend(request):
    body = json.loads(request.content)
    return httpx.Response(
        200, json={"accepted": len(body.get("records", [])), "renewed": True, "context_events": []}
    )


async def manager_for(settings):
    m = Manager(settings)
    await m.control_client.aclose()
    m.control_client = httpx.AsyncClient(
        transport=httpx.MockTransport(mock_backend), base_url=settings.api_base_url
    )
    return m


async def test_parallel_sessions_and_busy_rejection(settings):
    settings.max_concurrent_calls = 2
    m = await manager_for(settings)
    try:
        first = await m.prepare(prepared())
        second = await m.prepare(prepared())
        assert first.run_id != second.run_id and first.spool is not second.spool
        with pytest.raises(HTTPException) as error:
            await m.prepare(prepared())
        assert error.value.status_code == 409
        await first.finish({})
        assert not second.closed.is_set()
        third = await m.prepare(prepared())
        assert third.state == "prepared"
    finally:
        await m.close()


async def test_duplicate_start_does_not_spawn_twice(settings):
    m = await manager_for(settings)
    try:
        body = prepared()
        s = await m.prepare(body)
        assert await m.prepare(body) is s
        await m.start(s)
        await m.start(s)
        assert s.state == "waiting_media" and s.task is None
        other = body.model_copy(update={"generation": uuid4()})
        with pytest.raises(HTTPException):
            await m.prepare(other)
    finally:
        await m.close()


async def test_production_rejects_modem_before_hardware(settings):
    settings.env = "production"
    settings.hosted_calls_enabled = True
    m = await manager_for(settings)
    try:
        with pytest.raises(HTTPException) as error:
            await m.prepare(prepared("sim7600"))
        assert error.value.status_code == 404
    finally:
        await m.close()


async def test_production_prepares_twilio_without_dialing(settings):
    settings.env = "production"
    settings.hosted_calls_enabled = True
    settings.runtime_public_base_url = "https://runtime.example.com"
    m = await manager_for(settings)
    try:
        request = prepared("twilio").model_copy(
            update={"api_public_base_url": "https://api.example.com"}
        )
        session = await m.prepare(request)
        assert session.state == "prepared"
        assert session.task is None
    finally:
        await m.close()


async def test_overlapping_modem_ports_reject(settings):
    m = await manager_for(settings)
    try:
        first = await m.prepare(
            prepared(
                "sim7600", {"_resolved": {"endpoint": {"at_port": "COM3", "audio_port": "COM4"}}}
            )
        )
        with pytest.raises(HTTPException):
            await m.prepare(
                prepared(
                    "sim7600",
                    {"_resolved": {"endpoint": {"at_port": "com4", "audio_port": "COM5"}}},
                )
            )
        assert not first.connected
    finally:
        await m.close()


async def test_stale_boot_and_expired_grants(settings):
    m = await manager_for(settings)
    try:
        body = prepared()
        body.expires_at = time.time() - 1
        with pytest.raises(HTTPException):
            await m.prepare(body)
        s = await m.prepare(prepared())
        with pytest.raises(HTTPException):
            m.get(s.run_id, s.generation, uuid4())
    finally:
        await m.close()


async def test_api_stall_does_not_block_runtime_loop(settings):
    m = await manager_for(settings)
    gate = asyncio.Event()

    async def slow(request):
        await gate.wait()
        return await mock_backend(request)

    try:
        s = await m.prepare(prepared())
        await m.control_client.aclose()
        m.control_client = httpx.AsyncClient(
            transport=httpx.MockTransport(slow), base_url=settings.api_base_url
        )
        sync = asyncio.create_task(s.sync())
        ticks = 0
        for _ in range(10):
            await asyncio.sleep(0.01)
            ticks += 1
        assert ticks == 10 and not sync.done()
        gate.set()
        await sync
    finally:
        gate.set()
        await m.close()


async def test_lease_expiry_finishes_waiting_call(settings):
    m = await manager_for(settings)
    try:
        s = await m.prepare(prepared())
        await m.start(s)
        s.delivery_task.cancel()
        await asyncio.gather(s.delivery_task, return_exceptions=True)
        s.lease_until = time.monotonic() - 1
        await asyncio.wait_for(s.closed.wait(), 3)
        assert s.state == "ended"
        assert s.request.credentials == {}
        assert s.tracker._secrets == ()
        assert not s.request.grant.get_secret_value() and s.host is None
    finally:
        await m.close()


@pytest.mark.parametrize("full", [False, True])
def test_redaction_precedes_truncation(monkeypatch, full):
    monkeypatch.setenv("VOICE_INBOUND_API_LOGS_NO_TRUNCATE", str(full))
    monkeypatch.setenv("VOICE_API_LOG_MAX_BODY_CHARS", "128")
    value = {
        "api_key": "sk-secret",
        "prompt": "private prompt",
        "transcript": "private caller",
        "duration_ms": 3,
        "rows": [{"phone": "123456", "ok": True}] * 100,
    }
    preview = body_preview(json.dumps(value).encode(), "inbound")
    rendered = json.dumps(preview)
    assert (
        "sk-secret" not in rendered
        and "private caller" not in rendered
        and "123456" not in rendered
    )
    assert preview.get("truncated", False) is (not full)
    if full:
        assert len(preview["rows"]) == 100


async def test_binary_stream_is_not_buffered_for_logging(monkeypatch):
    monkeypatch.setenv("VOICE_ENABLE_INBOUND_API_LOGS", "true")
    delivered = []

    async def app(scope, receive, send):
        event = await receive()
        assert event["body"] == b"audio-secret"
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"audio/wav")],
            }
        )
        await send({"type": "http.response.body", "body": b"audio-secret"})

    async def receive():
        return {"type": "http.request", "body": b"audio-secret"}

    async def send(event):
        delivered.append(event)

    await HttpLoggingMiddleware(app, "test")(
        {
            "type": "http",
            "path": "/upload",
            "method": "POST",
            "headers": [(b"content-type", b"audio/wav")],
        },
        receive,
        send,
    )
    assert delivered[-1]["body"] == b"audio-secret"


def test_runtime_has_no_database_or_api_imports():
    root = Path(__file__).resolve().parents[2]
    for package in (root / "apps/runtime", root / "packages/voice_runtime"):
        for p in package.rglob("*.py"):
            text = p.read_text(encoding="utf-8")
            assert "from voice_api" not in text and "import voice_api" not in text, p
            assert "from sqlalchemy" not in text, p


@pytest.mark.parametrize(
    "inbound,outbound,full",
    [(a, b, c) for a in (False, True) for b in (False, True) for c in (False, True)],
)
def test_all_logging_combinations_keep_secrets_private(monkeypatch, inbound, outbound, full):
    monkeypatch.setenv("VOICE_ENABLE_INBOUND_API_LOGS", str(inbound))
    monkeypatch.setenv("VOICE_ENABLE_OUTBOUND_API_LOGS", str(outbound))
    for direction in ("inbound", "outbound"):
        monkeypatch.setenv("VOICE_" + direction.upper() + "_API_LOGS_NO_TRUNCATE", str(full))
        result = body_preview(
            b'{"api_key":"super-secret","signed_url":"https://private?token=secret","input":{"prompt":"private prompt"},"duration_ms":2}',
            direction,
        )
        text = json.dumps(result)
        assert (
            "super-secret" not in text
            and "private prompt" not in text
            and "https://private" not in text
        )
        assert result["duration_ms"] == 2


def test_capacity_pressure_blocks_admission_and_recovers(settings, monkeypatch):
    from voice_runner.capacity import Capacity

    capacity = Capacity(settings)
    monkeypatch.setattr(capacity.process, "cpu_percent", lambda: 0)
    pressure = {"audio_queue_pressure": 0.9}
    capacity.pressure = lambda: pressure
    capacity.sample(0)
    assert not capacity.allows(0)
    pressure["audio_queue_pressure"] = 0
    capacity.sample(0)
    capacity.sample(0)
    assert not capacity.allows(0)
    capacity.sample(0)
    assert capacity.allows(0)


async def test_isolated_pipeline_tasks_continue_during_15_second_api_delay(settings):
    from types import SimpleNamespace

    m = await manager_for(settings)
    first = await m.prepare(prepared())
    second = await m.prepare(prepared())
    ticks = {first.run_id: 0, second.run_id: 0}

    async def prepare(snapshot, tracker, **kwargs):
        pass

    async def close():
        pass

    for session in (first, second):

        async def converse(media, identity=session.run_id):
            while True:
                ticks[identity] += 1
                await asyncio.sleep(0.02)

        host = SimpleNamespace(
            prepare=prepare,
            converse=converse,
            close=close,
            settings=None,
            directory=Path(settings.recordings_dir) / session.run_id,
        )

        def make_host(session=session, host=host):
            session.host = host
            return host

        session.make_host = make_host

    async def delayed(request):
        await asyncio.sleep(15)
        return await mock_backend(request)

    await m.control_client.aclose()
    m.control_client = httpx.AsyncClient(
        transport=httpx.MockTransport(delayed), base_url=settings.api_base_url
    )
    tasks = [asyncio.create_task(s.run_pipeline(object())) for s in (first, second)]
    try:
        await asyncio.sleep(15.2)
        assert min(ticks.values()) > 300
        await m.control_client.aclose()
        m.control_client = httpx.AsyncClient(
            transport=httpx.MockTransport(mock_backend), base_url=settings.api_base_url
        )
        tasks[0].cancel()
        await asyncio.wait_for(tasks[0], 5)
        assert first.closed.is_set() and not tasks[1].done()
    finally:
        await m.close()
        await asyncio.gather(*tasks, return_exceptions=True)


def test_compiled_flow_accepts_pinned_json_without_recompilation():
    from voice_runtime.execution.pipecat_flow import compile_pipecat_flow
    from voice_shared.compiler import compile_flow_json

    snapshot = {
        "system_prompt": "Help callers",
        "flow": {
            "initial_node": "greeting",
            "nodes": [
                {"id": "greeting", "transitions": ["done"]},
                {"id": "done", "terminal": True},
            ],
        },
    }
    snapshot["_compiled_flow"] = compile_flow_json(snapshot)
    flow = compile_pipecat_flow(snapshot)
    assert "go_to_done" in str(flow.node("greeting"))
    assert "terminal response" in str(flow.node("done"))


def test_runtime_browser_single_use_ticket_and_binary_round_trip(settings, monkeypatch):
    import voice_runner.main as runtime_module
    from fastapi.testclient import TestClient
    from pipecat.frames.frames import InputAudioRawFrame, OutputAudioRawFrame
    from pipecat.serializers.protobuf import ProtobufFrameSerializer
    from starlette.websockets import WebSocketDisconnect
    from voice_runner.session import Session

    monkeypatch.setattr(runtime_module, "get_settings", lambda: settings)

    async def sync(self, records=None):
        return len(records or [])

    monkeypatch.setattr(Session, "sync", sync)

    async def echo(self, transport=None, media=None):
        self.task = asyncio.current_task()
        self.connected = True
        self.state = "running"
        socket = transport._client._websocket
        serializer = ProtobufFrameSerializer()
        frame = await serializer.deserialize(await socket.receive_bytes())
        assert isinstance(frame, InputAudioRawFrame)
        await socket.send_bytes(
            await serializer.serialize(
                OutputAudioRawFrame(frame.audio, frame.sample_rate, frame.num_channels)
            )
        )
        await self.finish({})

    monkeypatch.setattr(Session, "run_pipeline", echo)
    request = prepared()
    body = request.model_dump(mode="json")
    headers = {"X-Voice-Runtime-Control-Token": "control-secret"}
    serializer = ProtobufFrameSerializer()
    payload = asyncio.run(serializer.serialize(OutputAudioRawFrame(b"\0\0" * 160, 16000, 1)))
    with TestClient(runtime_module.app) as client:
        assert client.get("/v1/status").status_code == 401
        response = client.post("/v1/sessions", json=body, headers=headers)
        assert response.status_code == 200, response.text
        identity = {
            "run_id": body["run_id"],
            "generation": body["generation"],
            "boot_id": response.json()["boot_id"],
        }
        assert client.post("/v1/sessions/start", json=identity, headers=headers).status_code == 200
        ticket = client.post("/v1/sessions/browser-ticket", json=identity, headers=headers).json()[
            "ticket"
        ]
        url = f"/v1/browser/{body['run_id']}?ticket={ticket}"
        with client.websocket_connect(url, headers={"origin": "http://localhost:5173"}) as ws:
            ws.send_bytes(payload)
            response = asyncio.run(serializer.deserialize(ws.receive_bytes()))
            assert response.audio == b"\0\0" * 160
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(url, headers={"origin": "http://localhost:5173"}):
                pass


def test_paused_text_session_requests_checkpoint_resume():
    from types import SimpleNamespace

    from fastapi import HTTPException
    from voice_runner.main import ticket
    from voice_shared.contracts import SessionIdentity

    identity = SessionIdentity(run_id=uuid4(), generation=uuid4(), boot_id=uuid4())
    session = SimpleNamespace(
        generation=str(identity.generation),
        request=SimpleNamespace(channel="text_test"),
        text=SimpleNamespace(paused=True),
    )
    manager = SimpleNamespace(get=lambda *_args: session)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(manager=manager)))
    with pytest.raises(HTTPException) as error:
        asyncio.run(ticket(identity, request))
    assert error.value.status_code == 404


async def test_uncertain_modem_cleanup_retains_ports_after_secret_snapshot_release(settings):
    from unittest.mock import AsyncMock

    m = await manager_for(settings)
    try:
        first = await m.prepare(
            prepared(
                "sim7600", {"_resolved": {"endpoint": {"at_port": "COM3", "audio_port": "COM4"}}}
            )
        )
        first.driver = type(
            "Driver", (), {"close": AsyncMock(return_value={"release_confirmed": False})}
        )()
        await first.finish({})
        assert first.state == "uncertain" and first.closed.is_set()
        assert not first.request.snapshot and not first.request.credentials
        assert first.modem_ports == {"com3", "com4"}
        with pytest.raises(HTTPException) as error:
            await m.prepare(
                prepared(
                    "sim7600",
                    {"_resolved": {"endpoint": {"at_port": "com4", "audio_port": "COM5"}}},
                )
            )
        assert error.value.status_code == 409
    finally:
        await m.close()
