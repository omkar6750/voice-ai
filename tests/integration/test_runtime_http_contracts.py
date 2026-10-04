"""Independent runtime API contracts against an isolated PostgreSQL database."""

import hashlib
import io
import wave
from datetime import timedelta
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select
from test_evidence_ingestion import browser_run
from voice_api.api.deps import get_session
from voice_api.api.v1.endpoints import runtime, runtime_artifacts
from voice_api.core.runtime_config import RuntimeControlSettings
from voice_api.models import Run, RuntimeAssignment, TraceSpan
from voice_api.models.common import now


@pytest.fixture
async def remote(client, database, monkeypatch, tmp_path):
    run_id = await browser_run(client)
    run = await database.get(Run, run_id)
    run.resolved_config = {
        "_resolved": {
            "pipeline_logs_enabled": True,
            "tools": {
                "test_tool": {
                    "definition": {"kind": "registered", "parameters": {"type": "object"}}
                }
            },
        }
    }
    assignment = RuntimeAssignment(
        run_id=run_id,
        org_id=run.org_id,
        generation=str(uuid4()),
        boot_id=str(uuid4()),
        grant_hash=hashlib.sha256(b"session-secret").hexdigest(),
        expires_at=now() + timedelta(minutes=15),
        lease_expires_at=now() + timedelta(seconds=30),
        state="active",
        metrics={},
        diagnostic_sequence=0,
    )
    database.add(assignment)
    await database.commit()
    settings = RuntimeControlSettings(
        _env_file=None,
        runtime_service_token="service-secret",
        runtime_service_token_previous="",
        recordings_dir=str(tmp_path),
        env="dev",
        recording_max_bytes=1000000,
    )
    monkeypatch.setattr(runtime, "get_settings", lambda: settings)
    monkeypatch.setattr(runtime_artifacts, "get_settings", lambda: settings)

    async def credentials_live(*args):
        return True

    monkeypatch.setattr(runtime, "credentials_live", credentials_live)
    app = FastAPI()
    app.include_router(runtime.router, prefix="/api/v1")
    app.include_router(runtime_artifacts.router, prefix="/api/v1")

    async def db():
        yield database

    app.dependency_overrides[get_session] = db
    identity = {
        "run_id": run_id,
        "generation": assignment.generation,
        "boot_id": assignment.boot_id,
        "grant": "session-secret",
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"X-Voice-Runtime-Token": "service-secret"},
    ) as api:
        yield api, identity, assignment, tmp_path


async def test_sync_commit_replay_and_stale_ownership(remote, database):
    api, identity, assignment, _ = remote
    op_id = str(uuid4())
    record = {
        "kind": "operation_started",
        "id": str(uuid4()),
        "run_id": identity["run_id"],
        "timestamp_ns": 1,
        "operation_id": op_id,
        "name": "greeting",
        "category": "llm",
        "started_ns": 1,
    }
    body = {**identity, "records": [record]}
    for _ in range(2):
        response = await api.post("/api/v1/runtime/sync", json=body)
        assert response.status_code == 200, response.text
        assert response.json()["accepted"] == 1 and response.json()["renewed"]
    assert (
        await database.scalar(
            select(func.count()).select_from(TraceSpan).where(TraceSpan.id == op_id)
        )
        == 1
    )
    response = await api.post("/api/v1/runtime/sync", json={**body, "boot_id": str(uuid4())})
    assert response.status_code == 403
    assignment.lease_expires_at = now() - timedelta(seconds=1)
    await database.commit()
    response = await api.post("/api/v1/runtime/sync", json=identity)
    assert response.json()["stop"] and not response.json()["renewed"]


async def test_tool_retry_executes_external_action_once(remote, monkeypatch):
    api, identity, _, _ = remote
    from voice_api.services.runtime_tools import BackendToolDispatch

    calls = []

    async def action(args, flow):
        calls.append(args)
        return {"status": "completed"}

    monkeypatch.setattr(BackendToolDispatch, "_handler", lambda self, name: action)
    body = {
        **identity,
        "invocation_id": str(uuid4()),
        "name": "test_tool",
        "arguments": {"value": 1},
    }
    for _ in range(2):
        response = await api.post("/api/v1/runtime/tools", json=body)
        assert response.status_code == 200, response.text
    assert len(calls) == 1
    response = await api.post("/api/v1/runtime/tools", json={**body, "arguments": {"value": 2}})
    assert response.status_code == 409 and len(calls) == 1


async def test_artifact_stream_integrity_and_replayed_completion(remote):
    api, identity, _, _ = remote
    data = io.BytesIO()
    with wave.open(data, "wb") as wav:
        wav.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
        wav.writeframes(b"\0\0" * 80)
    payload = data.getvalue()
    body = {
        **identity,
        "artifact_id": str(uuid4()),
        "kind": "input",
        "size_bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "sample_rate": 8000,
        "channels": 1,
        "sample_width": 2,
        "duration_seconds": 0.01,
    }
    response = await api.post("/api/v1/runtime/artifacts/grant", json=body)
    assert response.status_code == 200, response.text
    url = response.json()["upload_url"]
    headers = {
        "X-Voice-Session-Grant": identity["grant"],
        "X-Voice-Generation": identity["generation"],
        "X-Voice-Boot": identity["boot_id"],
    }
    response = await api.put(url, headers=headers, content=payload[:-2])
    assert response.status_code == 422, response.text
    assert (await api.put(url, headers=headers, content=payload)).status_code == 200
    for _ in range(2):
        response = await api.post("/api/v1/runtime/artifacts/complete", json=body)
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "available"
    assert (
        await api.post("/api/v1/runtime/artifacts/grant", json={**body, "sha256": "0" * 64})
    ).status_code == 409


async def test_late_confirmed_cleanup_reconciles_expired_run_without_restart(remote, database):
    from voice_api.services.runtime_recovery import recover_expired_assignments

    api, identity, assignment, _ = remote
    run = await database.get(Run, identity["run_id"])
    run.status = "running"
    assignment.lease_expires_at = now() - timedelta(minutes=1)
    await database.commit()
    assert await recover_expired_assignments(database, run.id) == 1
    assert run.status == "uncertain"
    body = {
        **identity,
        "lifecycle": {
            "termination": {
                "cause": "terminal_completed",
                "pipeline_finished_at_ns": 10,
                "cleanup_status": "confirmed",
            }
        },
    }
    response = await api.post("/api/v1/runtime/sync", json=body)
    assert response.status_code == 200, response.text
    assert run.status == "completed" and run.ended_at is not None
    assert assignment.state == "ended"
    response = await api.post("/api/v1/runtime/sync", json=body)
    assert response.status_code == 200, response.text
    assert run.status == "completed" and assignment.state == "ended"
