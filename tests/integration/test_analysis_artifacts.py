"""Derived evidence and retention use isolated rows/files, never real recordings."""

import wave
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from voice_api.core.config import get_settings
from voice_api.models import ConversationMessage, Exchange, RunArtifact, TraceSpan
from voice_api.models.common import new_id


async def create_run(client, *, logging_override=None):
    config = {
        "name": "test",
        "flow": {"initial_node": "greeting", "nodes": [{"id": "greeting", "terminal": True}]},
    }
    agent = (await client.post("/api/agents", json={"name": new_id(), "config": config})).json()
    version = agent["version_id"]
    await client.post(f"/api/agent-versions/{version}/publish", json={"revision": 1})
    body = {"agent_version_id": version}
    if logging_override is not None:
        body["logging_override"] = logging_override
    return (await client.post("/api/runs", json=body)).json()["run_id"]


async def test_analysis_sources_replay_and_failure(client, database):
    run_id = await create_run(client)
    exchange_id, message_id, operation_id = new_id(), new_id(), new_id()
    database.add(Exchange(id=exchange_id, run_id=run_id, sequence=1, origin="caller"))
    await database.flush()
    database.add(
        ConversationMessage(
            id=message_id,
            run_id=run_id,
            exchange_id=exchange_id,
            sequence=1,
            role="user",
            content="Tell me more",
        )
    )
    database.add(
        TraceSpan(
            id=operation_id, run_id=run_id, category="llm", name="classifier", status="failed"
        )
    )
    await database.commit()
    body = {
        "kind": "classification",
        "id": new_id(),
        "operation_id": operation_id,
        "source_message_ids": [message_id],
        "occurred_at": datetime.now(UTC).isoformat(),
        "status": "failed",
        "evidence": {"error": "provider unavailable"},
    }
    path = f"/api/runs/{run_id}/analysis"
    for _ in range(2):
        response = await client.post(path, json=body)
        assert response.status_code == 201, response.text
    rows = (await client.get(path)).json()["classifications"]
    assert len(rows) == 1 and rows[0]["verdict"] is None
    assert (await client.post(path, json={**body, "verdict": "hot"})).status_code == 422
    assert (
        await client.post(path, json={**body, "id": new_id(), "source_message_ids": [new_id()]})
    ).status_code == 422
    with pytest.raises(IntegrityError):
        async with database.begin_nested():
            await database.execute(
                text("UPDATE classifications SET verdict='hot' WHERE id=:id AND org_id=:org_id"),
                {"id": body["id"], "org_id": database.sync_session.info["organization_scope_id"]},
            )


async def test_artifact_retention_and_disabled_logs(client, database, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "recordings_dir", str(tmp_path))
    run_id = await create_run(client, logging_override=False)
    folder = tmp_path / run_id
    folder.mkdir()
    with wave.open(str(folder / "input.wav"), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b"\x00\x00" * 320)
    body = {"id": new_id(), "kind": "input", "path": f"{run_id}/input.wav"}
    path = f"/api/runs/{run_id}/artifacts"
    response = await client.post(path, json=body)
    assert response.status_code == 201, response.text
    assert (await client.get(f"/api/artifacts/{body['id']}/file")).status_code == 200
    disabled_log = await client.post(
        path,
        json={"id": new_id(), "kind": "pipeline_log", "path": f"{run_id}/pipeline.log"},
    )
    assert disabled_log.status_code == 409, disabled_log.text
    assert (
        await client.post(path, json={**body, "id": new_id(), "path": "../secret.wav"})
    ).status_code == 422
    row = await database.get(RunArtifact, body["id"])
    assert row.sample_rate == 16000 and row.duration_seconds == 0.02
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await database.commit()
    media = tmp_path / "reusable.bin"
    media.write_bytes(b"keep")
    assert (await client.post("/api/artifacts/expire")).json() == {"deleted": 1, "failed": 0}
    assert not (folder / "input.wav").exists() and media.exists()
    assert (await client.get(f"/api/artifacts/{body['id']}/file")).status_code == 410
    assert (await client.post("/api/artifacts/expire")).json()["deleted"] == 0
