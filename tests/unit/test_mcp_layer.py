"""Protocol, schema and transport regressions without providers or hardware."""

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException, Request
from voice_api.api.v1.endpoints.chat import compact_test_events
from voice_api.core.clerk_auth import ClerkPrincipal, require_clerk_user
from voice_api.core.config import get_settings
from voice_api.main import app
from voice_api.mcp_server import MANIFEST, McpApplication, registry, resolve_schema
from voice_api.schemas.chat import ChatTestTurn
from voice_api.services.mcp_auth import McpActor, connection_info
from voice_api.services.run_debug import bounded, offset
from voice_runtime.execution.exchange import ExchangeTracker
from voice_shared.contracts import TextTestCommand

from voice_shared import request_evidence


def test_operation_inventory_is_complete_and_credentials_are_read_only():
    inventory = json.loads(MANIFEST.read_text())
    keys = {
        f"{method.upper()} {path}"
        for path, methods in app.openapi()["paths"].items()
        for method in methods
    }
    assert keys == inventory.keys()
    for key, review in inventory.items():
        if "credentials" in key and not key.startswith("GET "):
            assert review["access"] == "exclude"
        if any(
            part in key
            for part in ("secrets", "disconnect", "reconnect", "/platform/", "mcp-tokens")
        ):
            assert review["access"] == "exclude"
    assert inventory["DELETE /api/v1/integrations/{connection_id}"]["access"] == "exclude"
    assert inventory["DELETE /api/v1/calendar-integrations/{integration_id}"]["access"] == "exclude"


def test_tool_schemas_only_include_reachable_definitions():
    schema = resolve_schema(
        {
            "$ref": "#/components/schemas/A",
            "$defs": {
                "A": {"$ref": "#/components/schemas/B"},
                "B": {"type": "string"},
                "Unused": {"type": "object"},
            },
        }
    )
    assert set(schema["$defs"]) == {"A", "B"}
    tools = registry(app)
    assert {
        "inspect_run",
        "inspect_operations",
        "get_run_config",
        "read_run_logs",
        "chat_test_turn",
    } <= tools.keys()
    assert tools["inspect_run"]["schema"]["properties"]["max_chars"]["default"] == 1_000_000
    assert (
        "materialize_context"
        in tools["inspect_operations"]["schema"]["$defs"]["EvidenceSelection"]["properties"]
    )
    assert (
        "caller_message" in tools["chat_test_turn"]["schema"]["$defs"]["ChatTestTurn"]["properties"]
    )


def test_chat_test_turn_requires_one_saved_version_or_existing_conversation():
    from uuid import uuid4

    from pydantic import ValidationError

    assert ChatTestTurn(agent_version_id=uuid4()).agent_version_id
    assert ChatTestTurn(conversation_id=uuid4(), caller_message="Hello").conversation_id
    with pytest.raises(ValidationError):
        ChatTestTurn(conversation_id=uuid4())
    with pytest.raises(ValidationError):
        ChatTestTurn(agent_version_id=uuid4(), conversation_id=uuid4())


def test_text_test_command_contract_requires_message_for_caller_turn():
    from uuid import uuid4

    from pydantic import ValidationError

    identity = {
        "run_id": str(uuid4()),
        "generation": str(uuid4()),
        "boot_id": str(uuid4()),
    }
    command = TextTestCommand(**identity, id="cmd-1", type="user_message", text="Hello")
    assert command.text == "Hello"
    with pytest.raises(ValidationError):
        TextTestCommand(**identity, id="cmd-2", type="user_message")


def test_chat_test_turn_compacts_transcript_tool_activity_and_errors():
    result = compact_test_events(
        [
            {
                "type": "message",
                "kind": "user",
                "payload": {"text": "We sell jewellery", "status": "completed"},
            },
            {
                "type": "message",
                "kind": "assistant",
                "payload": {"text": "Who buys from you today?", "status": "completed"},
            },
            {
                "type": "message",
                "kind": "evidence",
                "payload": {"kind": "tool_started", "name": "classify_lead", "status": "started"},
            },
            {
                "type": "error",
                "stage": "provider",
                "message": "provider detail",
                "diagnostic_id": "diag-1",
            },
        ]
    )
    assert [item["role"] for item in result["transcript"]] == ["user", "assistant"]
    assert result["tool_activity"][0]["name"] == "classify_lead"
    assert result["errors"][0]["message"] == "provider detail"


@pytest.mark.parametrize(
    "base",
    [
        "http://example.com",
        "https://example.com/path",
        "https://user:pass@example.com",
        "https://example.com?token=x",
    ],
)
def test_connection_rejects_unsafe_origins(monkeypatch, base):
    monkeypatch.setattr(get_settings(), "mcp_local_base_url", base)
    with pytest.raises(HTTPException):
        connection_info("org_test")


def test_connection_is_environment_specific(monkeypatch):
    monkeypatch.setattr(get_settings(), "env", "prod")
    monkeypatch.setattr(get_settings(), "mcp_public_base_url", "https://api.example.com")
    info = connection_info("org_test")
    assert info["url"] == "https://api.example.com/mcp"
    assert info["env_var"].endswith("_PROD")
    assert "--bearer-token-env-var" in info["command"]


def test_http_payload_capture_is_opt_in_and_bounded(monkeypatch):
    monkeypatch.setenv("VOICE_ENV", "prod")
    assert request_evidence.json_payload(b'{"messages":[]}') is None
    token = request_evidence.capture_payloads.set(True)
    try:
        assert request_evidence.json_payload(b'{"messages":[]}') == {"messages": []}
        assert request_evidence.json_payload(b"not json") is None
        assert request_evidence.json_payload(b"x" * 1_000_001) is None
    finally:
        request_evidence.capture_payloads.reset(token)


async def test_actual_transport_hooks_capture_with_optional_logging_disabled(monkeypatch):
    import aiohttp
    import httplib2
    import requests
    from websockets.asyncio.client import connect

    from voice_shared import http_clients

    async def http_send(self, request, **kwargs):
        return httpx.Response(200, json={"answer": "done"})

    async def aio_send(self, method, url, **kwargs):
        return SimpleNamespace(status=503)

    async def ws_connect(self):
        raise ConnectionError("private provider failure")

    # Register each global patch with monkeypatch before the installer wraps it.
    monkeypatch.setattr(http_clients, "_installed", False)
    monkeypatch.setattr(httpx.AsyncClient, "send", http_send)
    monkeypatch.setattr(httpx.Client, "send", httpx.Client.send)
    monkeypatch.setattr(requests.Session, "send", requests.Session.send)
    monkeypatch.setattr(httplib2.Http, "request", httplib2.Http.request)
    monkeypatch.setattr(aiohttp.ClientSession, "_request", aio_send)
    monkeypatch.setattr(connect, "create_connection", ws_connect)
    monkeypatch.setattr(http_clients, "enabled", lambda name: False)
    events = []
    token = request_evidence.sink.set(events.append)
    try:
        http_clients.install("voice-runtime")
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions?key=private", json={"messages": []}
            )
        assert response.json() == {"answer": "done"}
        await aiohttp.ClientSession._request(None, "POST", "https://api.sarvam.ai/speech")
        with pytest.raises(ConnectionError):
            await connect.create_connection(
                SimpleNamespace(uri="wss://speech.gnani.ai/stt?key=private")
            )
    finally:
        request_evidence.sink.reset(token)
    assert len(events) == 6
    assert {event["service"] for event in events} == {"openai", "sarvam", "gnani"}
    assert "private" not in json.dumps(
        [{k: v for k, v in event.items() if k != "callback"} for event in events]
    )
    assert events[-1]["status"] == "failed"
    assert events[-1]["category"] == "provider_connection"
    assert events[-1]["timing_scope"] == "connection_setup"


async def test_http_header_cannot_supply_internal_principal(monkeypatch):
    monkeypatch.setattr(get_settings(), "clerk_secret_key", None)
    request = Request({"type": "http", "headers": [(b"voice.mcp_principal", b"org:admin")]})
    with pytest.raises(HTTPException):
        await require_clerk_user(request)


def test_chunks_reconstruct_and_detect_changed_evidence():
    value = {"text": "hello " * 1000}
    first = bounded(value, max_chars=1024)
    chunks, cursor = [first["text"]], first["next_offset"]
    while cursor is not None:
        part = bounded(value, cursor, 1024, first["sha256"])
        chunks.append(part["text"])
        cursor = part["next_offset"]
    assert json.loads("".join(chunks)) == value
    with pytest.raises(HTTPException) as error:
        bounded({"changed": True}, expected_hash=first["sha256"])
    assert error.value.status_code == 409


def test_timing_preserves_overlap_and_unknown_values():
    origin = datetime.now(UTC)
    assert offset(None, origin) is None
    assert offset(origin - timedelta(milliseconds=5), origin) == -5


def test_request_attempts_freeze_exchange_and_do_not_capture_credentials():
    records = []
    tracker = ExchangeTracker("test-run", SimpleNamespace(submit=records.append))
    tracker.begin("caller")
    first_exchange = tracker.current
    token = request_evidence.sink.set(tracker.request_attempt)
    try:
        state = request_evidence.begin("POST", "/v1/chat/completions?key=secret", "provider")
        tracker.begin("caller")
        request_evidence.finish(state, status=429)
    finally:
        request_evidence.sink.reset(token)
    request_records = [r for r in records if r.get("category") == "http_request"]
    assert len(request_records) == 2
    assert request_records[0]["operation_id"] == request_records[1]["operation_id"]
    assert request_records[1]["exchange_id"] == first_exchange
    assert request_records[1]["status"] == "failed"
    assert "secret" not in json.dumps(request_records)


async def test_stream_capture_does_not_consume_and_reports_completion():
    events = []
    token = request_evidence.sink.set(events.append)

    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"part1"
            yield b"part2"

        async def aclose(self):
            pass

    try:
        state = request_evidence.begin("POST", "/chat/completions", "provider")
        stream = request_evidence.AsyncResponseStream(Stream(), state, 200)
        assert len(events) == 1
        assert b"".join([chunk async for chunk in stream]) == b"part1part2"
        await stream.aclose()
        assert len(events) == 2
        assert events[-1]["timing_scope"] == "complete"
    finally:
        request_evidence.sink.reset(token)


async def test_stream_error_and_early_close_are_distinct():
    events = []
    token = request_evidence.sink.set(events.append)

    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            raise httpx.ReadError("contains-secret")
            yield b"unreachable"

        async def aclose(self):
            pass

    try:
        state = request_evidence.begin("GET", "/audio", "provider")
        stream = request_evidence.AsyncResponseStream(Stream(), state, 200)
        with pytest.raises(httpx.ReadError):
            async for _ in stream:
                pass
        assert events[-1]["error_type"] == "ReadError"
        assert "contains-secret" not in json.dumps(
            [{k: v for k, v in e.items() if k != "callback"} for e in events]
        )
        state = request_evidence.begin("GET", "/audio", "provider")
        await request_evidence.AsyncResponseStream(Stream(), state, 200).aclose()
        assert events[-1]["timing_scope"] == "closed_before_exhaustion"
    finally:
        request_evidence.sink.reset(token)


async def test_mcp_initialize_discovery_and_errors(monkeypatch):
    import voice_api.mcp_server as module

    actor = McpActor(ClerkPrincipal("user_test", "org_test", "org:member"), "u", "o", "t")

    async def auth(raw, **kwargs):
        if raw != "test-token":
            raise HTTPException(401, "Invalid token")
        return actor

    monkeypatch.setattr(module, "authenticate", auth)
    monkeypatch.setattr(get_settings(), "mcp_local_base_url", "http://127.0.0.1:8000")
    instance = McpApplication(app)
    instance.operations = registry(app)
    headers = {
        "Authorization": "Bearer test-token",
        "Accept": "application/json, text/event-stream",
    }
    async with (
        instance.manager.run(),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=instance), base_url="http://127.0.0.1:8000"
        ) as client,
    ):
        denied = await client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert denied.status_code == 401
        init = await client.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"},
                },
            },
        )
        assert init.status_code == 200, init.text
        assert init.json()["result"]["serverInfo"]["name"] == "voice-ai"
        listed = await client.post(
            "/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
        )
        assert listed.status_code == 200, listed.text
        assert "inspect_run" in {tool["name"] for tool in listed.json()["result"]["tools"]}
        called = await client.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "inspect_run", "arguments": {}},
            },
        )
        assert called.json()["result"]["isError"] is True, called.text
        assert "422" in called.text
        invalid_origin = await client.post(
            "/mcp", headers={**headers, "Origin": "https://evil.example"}, json={}
        )
        assert invalid_origin.status_code == 403
