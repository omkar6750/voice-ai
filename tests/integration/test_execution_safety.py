"""No hardware: callback claims, endpoint fencing and restart uncertainty."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from voice_api.models import Call, Run, WorkspaceSettings
from voice_api.models.common import new_id
from voice_api.services.resolution_service import fingerprint


async def setup_call(client):
    config = {
        "name": "test",
        "flow": {"initial_node": "greeting", "nodes": [{"id": "greeting", "terminal": True}]},
    }
    agent = (await client.post("/api/agents", json={"name": new_id(), "config": config})).json()
    version = agent["version_id"]
    assert (
        await client.post(f"/api/agent-versions/{version}/publish", json={"revision": 1})
    ).status_code == 200
    contact = (
        await client.post(
            "/api/contacts",
            json={
                "name": "test",
                "phone_number": "+1555" + str(int(new_id().replace("-", "")[:8], 16)),
                "timezone": "Asia/Kolkata",
            },
        )
    ).json()["id"]
    endpoint = (
        await client.post(
            "/api/runtime-endpoints",
            json={"name": new_id(), "config": {"at_port": "COM16", "audio_port": "COM17"}},
        )
    ).json()["id"]
    return {"contact_id": contact, "agent_version_id": version, "endpoint_id": endpoint}


async def test_claim_fencing_and_restart_do_not_redial(client, database):
    body = await setup_call(client)
    first = (await client.post("/api/calls", json=body)).json()
    second = (await client.post("/api/calls", json=body)).json()
    token = new_id()
    claim = {"token": token, "endpoint_id": body["endpoint_id"]}
    path = f"/api/runs/{first['run_id']}"
    response = await client.post(path + "/claim", json=claim)
    assert response.status_code == 200, response.text
    assert response.json()["call_id"] == first["call_id"]
    assert response.json()["config_hash"] == fingerprint(response.json()["resolved_config"])
    assert (await client.post(path + "/claim", json=claim)).status_code == 200
    assert (
        await client.post(f"/api/runs/{second['run_id']}/claim", json={**claim, "token": new_id()})
    ).status_code == 409
    assert (
        await client.post(path + "/progress", json={"token": "stale", "status": "running"})
    ).status_code == 409
    assert (
        await client.post(path + "/progress", json={"token": token, "status": "completed"})
    ).status_code == 422
    run = await database.get(Run, first["run_id"])
    run.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await database.commit()
    assert (await client.post(f"/api/runtime-endpoints/{body['endpoint_id']}/recover")).json()[
        "status"
    ] == "uncertain"
    assert (await client.post(path + "/claim", json=claim)).status_code == 409
    assert (
        await client.post(f"/api/runs/{second['run_id']}/claim", json={**claim, "token": new_id()})
    ).status_code == 409


async def test_explicit_reconciliation_releases_without_redial(client, database):
    body = await setup_call(client)
    run_id = (await client.post("/api/calls", json=body)).json()["run_id"]
    await client.post(
        f"/api/runs/{run_id}/claim", json={"token": new_id(), "endpoint_id": body["endpoint_id"]}
    )
    run = await database.get(Run, run_id)
    run.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await database.commit()
    await client.post(f"/api/runtime-endpoints/{body['endpoint_id']}/recover")
    path = f"/api/runs/{run_id}/reconcile"
    assert (
        await client.post(path, json={"transport_idle_verified": True, "note": "checked"})
    ).status_code == 422
    response = await client.post(
        path,
        json={
            "transport_idle_verified": True,
            "worker_stopped_verified": True,
            "note": "Worker stopped and modem idle",
        },
    )
    assert response.json() == {"status": "failed", "redialed": False}
    await database.refresh(run)
    assert run.ended_at is None and run.final_state["evidence_incomplete"]


async def test_callback_defaults_window_and_single_launch(client, database):
    body = await setup_call(client)
    scheduled = {
        "request_key": new_id(),
        "contact_id": body["contact_id"],
        "agent_version_id": body["agent_version_id"],
        "due_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
        "timezone": "Asia/Kolkata",
        "original_phrase": "Call me tomorrow",
    }
    response = await client.post("/api/callbacks", json=scheduled)
    assert response.status_code == 201, response.text
    callback_id = response.json()["id"]
    assert (await client.post("/api/callbacks", json=scheduled)).json()["id"] == callback_id
    launch = {"endpoint_id": body["endpoint_id"], "mode": "automatic"}
    path = f"/api/callbacks/{callback_id}/launch"
    assert (await client.post(path, json=launch)).status_code == 409
    settings = await database.scalar(select(WorkspaceSettings).where(WorkspaceSettings.id == 1))
    if settings is None:
        settings = WorkspaceSettings(id=1, config={})
        database.add(settings)
    settings.config = {"automatic_callbacks_enabled": True}
    await database.commit()
    accepted = await client.post(path, json=launch)
    assert accepted.status_code == 200, accepted.text
    assert (await client.post(path, json={**launch, "mode": "manual"})).status_code == 409
    call = await database.get(Call, accepted.json()["call_id"])
    assert call.agent_version_id == body["agent_version_id"]
    scheduled["request_key"] = new_id()
    scheduled["due_at"] = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    late = (await client.post("/api/callbacks", json=scheduled)).json()["id"]
    assert (await client.post(f"/api/callbacks/{late}/launch", json=launch)).status_code == 409
    assert (
        await client.post(f"/api/callbacks/{late}/launch", json={**launch, "mode": "manual"})
    ).status_code == 200


async def test_snapshot_logging_and_final_outcome(client, database):
    body = await setup_call(client)
    response = await client.post("/api/calls", json={**body, "logging_override": True})
    run_id = response.json()["run_id"]
    run = await database.get(Run, run_id)
    assert run.resolved_config["_resolved"]["pipeline_logs_enabled"] is True
    assert run.resolved_config["_resolved"]["application"]["dependencies"]["pydantic"]
    token = new_id()
    assert (
        await client.post(
            f"/api/runs/{run_id}/claim", json={"token": token, "endpoint_id": body["endpoint_id"]}
        )
    ).status_code == 200
    outcome = {
        "token": token,
        "status": "completed",
        "transport_released": True,
        "final_state": {"api_key": "not-for-storage", "node": "done"},
    }
    for _ in range(2):
        response = await client.post(f"/api/runs/{run_id}/progress", json=outcome)
        assert response.status_code == 200, response.text
    await database.refresh(run)
    assert run.final_state["api_key"] == "[REDACTED]"
    assert run.status == "completed"
