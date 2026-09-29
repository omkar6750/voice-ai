"""WebSocket handshake and protobuf wire tests without live provider credentials."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from pipecat.frames.frames import InputAudioRawFrame, OutputAudioRawFrame
from pipecat.serializers.protobuf import ProtobufFrameSerializer
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.websockets import WebSocketDisconnect
from voice_api.api.deps import get_session, require_legacy_owner
from voice_api.core.config import get_settings
from voice_api.main import app
from voice_api.models import BrowserSession, Run
from voice_api.services.browser_session_service import (
    BrowserSessionContext,
    BrowserSessionManager,
    _run_browser_pipeline,
)
from voice_runtime.execution.delivery import EvidenceFinalization


def test_websocket_auth_and_binary_audio_round_trip():
    browser_session = BrowserSession(
        id="browser-test", run_id="run-test", status="created", org_id="org-test"
    )
    run = Run(
        id="run-test",
        org_id="org-test",
        channel="browser",
        transport_provider="dashboard",
        status="claimed",
        agent_version_id="agent-version",
        resolved_config={"audio": {"sample_rate": 16000}},
    )
    db = AsyncMock(spec=AsyncSession)
    db.sync_session = SimpleNamespace(info={}, identity_map={})

    async def get(model, _pk):
        return browser_session if model is BrowserSession else run

    db.get.side_effect = get
    db.__aenter__.return_value = db

    async def db_dependency():
        yield db

    manager = BrowserSessionManager()
    app.dependency_overrides[get_session] = db_dependency
    app.dependency_overrides[require_legacy_owner] = lambda: None

    async def echo_pipeline(_ctx, transport, _settings):
        socket = transport._client._websocket
        serializer = ProtobufFrameSerializer()
        incoming = await serializer.deserialize(await socket.receive_bytes())
        assert isinstance(incoming, InputAudioRawFrame)
        reply = await serializer.serialize(
            OutputAudioRawFrame(incoming.audio, incoming.sample_rate, incoming.num_channels)
        )
        assert isinstance(reply, bytes)
        await socket.send_bytes(reply)

    try:
        with (
            patch("voice_api.services.browser_session_service.browser_session_manager", manager),
            patch("voice_api.services.browser_session_service.SessionFactory", return_value=db),
            patch(
                "voice_api.services.browser_session_service._run_browser_pipeline",
                side_effect=echo_pipeline,
            ),
            TestClient(app) as client,
        ):
            response = client.post("/api/v1/browser-sessions/browser-test/ticket")
            assert response.status_code == 200
            ticket = response.json()["ticket"]
            path = f"/api/v1/browser-sessions/browser-test/ws?ticket={ticket}"
            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect(path, headers={"origin": "https://evil.example"}):
                    pass
            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect(
                    "/api/v1/browser-sessions/wrong/ws?ticket=" + ticket,
                    headers={"origin": "http://localhost:5173"},
                ):
                    pass

            serializer = ProtobufFrameSerializer()
            audio = b"\x01\x00" * 320
            outgoing = asyncio.run(serializer.serialize(OutputAudioRawFrame(audio, 16000, 1)))
            assert isinstance(outgoing, bytes)
            with client.websocket_connect(
                path, headers={"origin": "http://localhost:5173"}
            ) as socket:
                socket.send_bytes(outgoing)
                returned = asyncio.run(serializer.deserialize(socket.receive_bytes()))
                assert isinstance(returned, InputAudioRawFrame)
                assert returned.audio == audio
            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect(path, headers={"origin": "http://localhost:5173"}):
                    pass
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_ticket_expiration_and_one_active_call(monkeypatch):
    manager = BrowserSessionManager()
    clock = [100.0]
    monkeypatch.setattr(
        "voice_api.services.browser_session_service.time.monotonic", lambda: clock[0]
    )
    first = await manager.issue_ticket("one", "run-one", {}, "org-test")
    with pytest.raises(Exception, match="Another browser call is active"):
        await manager.issue_ticket("two", "run-two", {}, "org-test")
    clock[0] = 131.0
    assert await manager.consume_ticket("one", first) is None
    second = await manager.issue_ticket("two", "run-two", {}, "org-test")
    assert await manager.consume_ticket("one", second) is None
    assert await manager.consume_ticket("two", second) is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_error", [False, True])
async def test_pipeline_finalizes_disconnect_or_provider_failure(tmp_path, provider_error):
    ctx = BrowserSessionContext(
        "browser-test", "run-test", {"audio": {"sample_rate": 16000}}, "org-test"
    )
    run = Run(id="run-test", status="running", channel="browser", resolved_config={})
    browser_session = BrowserSession(id="browser-test", run_id="run-test", status="connected")
    db = AsyncMock(spec=AsyncSession)
    db.sync_session = SimpleNamespace(info={}, identity_map={})
    db.scalars.return_value = SimpleNamespace(all=lambda: [])
    db.scalar.return_value = None

    async def get(model, _pk):
        return browser_session if model is BrowserSession else run

    db.get.side_effect = get
    db.__aenter__.return_value = db
    host = AsyncMock()
    host.directory = tmp_path / "not-created"
    async def complete_call(*_args):
        ctx.termination.request("terminal_completed", graceful=True)
        ctx.termination.pipeline_finished()
        return {"termination": ctx.termination.snapshot()}

    host.converse.side_effect = complete_call
    if provider_error:
        host.prepare.side_effect = RuntimeError("provider offline")
    with (
        patch("voice_api.services.browser_session_service.SessionFactory", return_value=db),
        patch("voice_api.services.browser_session_service.NativePipelineHost", return_value=host),
        patch("voice_api.services.browser_session_service.DurableSpool"),
        patch("voice_api.services.browser_session_service.ExchangeTracker"),
        patch("voice_api.services.browser_session_service.stream_evidence", new_callable=AsyncMock),
        patch(
            "voice_api.services.browser_session_service.finalize_evidence",
            new_callable=AsyncMock,
            return_value=EvidenceFinalization(incomplete=False, diagnostic=None),
        ),
        patch(
            "voice_api.services.browser_session_service.persist_diagnostic",
            new_callable=AsyncMock,
        ) as diagnostic,
    ):
        await _run_browser_pipeline(ctx, object(), get_settings())
    host.close.assert_awaited_once()
    assert diagnostic.await_count >= 1
    assert run.status == ("failed" if provider_error else "completed")
    assert browser_session.status == ("failed" if provider_error else "disconnected")
    assert run.ended_at is not None
    db.commit.assert_awaited()
