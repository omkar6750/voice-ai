"""Prove evidence replay, ordering, provenance and interrupted visit behavior."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from voice_api.models import (
    Exchange,
    FlowNodeVisit,
    ToolInvocation,
    ToolInvocationResult,
    TraceSpan,
)
from voice_api.models.common import new_id


@pytest.fixture
async def run_id(client):
    agent = await client.post(
        "/api/agents",
        json={
            "name": new_id(),
            "config": {
                "name": "test",
                "flow": {
                    "initial_node": "greeting",
                    "nodes": [{"id": "greeting", "terminal": True}],
                },
            },
        },
    )
    assert agent.status_code == 201, agent.text
    version = agent.json()["version_id"]
    published = await client.post(f"/api/agent-versions/{version}/publish", json={"revision": 1})
    assert published.status_code == 200, published.text
    run = await client.post("/api/runs", json={"agent_version_id": version})
    assert run.status_code == 201, run.text
    return run.json()["run_id"]


@pytest.fixture
async def tool(database, run_id):
    value = ToolInvocation(
        id=new_id(),
        run_id=run_id,
        binding_key="lookup",
        idempotency_key=new_id(),
        started_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    database.add(value)
    await database.flush()
    return value


async def test_intermediate_and_null_final_result_replay(client, database, run_id, tool):
    path = f"/api/runs/{run_id}/tools/{tool.id}/results"
    first = {
        "id": new_id(),
        "sequence": 1,
        "payload": {},
        "is_final": False,
        "occurred_at": datetime.now(UTC).isoformat(),
    }
    final = {**first, "id": new_id(), "sequence": 2, "payload": None, "is_final": True}
    assert tool.result is None
    for body in (first, first, final, final):
        response = await client.post(path, json=body)
        assert response.status_code == 201, response.text
    assert await database.scalar(select(func.count()).select_from(ToolInvocationResult)) == 2
    assert (await client.post(path, json={**final, "payload": "changed"})).status_code == 409
    assert (
        await client.post(path, json={**first, "id": new_id(), "sequence": 3})
    ).status_code == 409
    timeline = (await client.get(f"/api/runs/{run_id}/timeline")).json()
    assert [r["payload"] for r in timeline["tool_results"]] == [{}, None]
    assert [r["is_final"] for r in timeline["tool_results"]] == [False, True]


async def test_result_sequence_and_sql_immutability(client, database, run_id, tool):
    path = f"/api/runs/{run_id}/tools/{tool.id}/results"
    body = {
        "id": new_id(),
        "sequence": 2,
        "payload": "done",
        "is_final": True,
        "occurred_at": datetime.now(UTC).isoformat(),
    }
    assert (await client.post(path, json=body)).status_code == 409
    body["sequence"] = 1
    assert (await client.post(path, json=body)).status_code == 201
    with pytest.raises(IntegrityError):
        async with database.begin_nested():
            await database.execute(
                text("UPDATE tool_invocation_results SET payload = '{}' WHERE id = :id"),
                {"id": body["id"]},
            )
    with pytest.raises(IntegrityError):
        async with database.begin_nested():
            database.add(
                ToolInvocationResult(
                    id=new_id(),
                    run_id=run_id,
                    tool_invocation_id=tool.id,
                    sequence=2,
                    payload={},
                    is_final=False,
                    occurred_at=datetime.now(UTC),
                )
            )
            await database.flush()


async def test_delayed_result_consumed_in_later_exchange(client, database, run_id, tool):
    initial = Exchange(id=new_id(), run_id=run_id, sequence=1, origin="caller")
    later = Exchange(id=new_id(), run_id=run_id, sequence=2, origin="caller")
    database.add_all([initial, later])
    await database.flush()
    tool.exchange_id = initial.id
    await database.flush()
    result = {
        "id": new_id(),
        "sequence": 1,
        "payload": {"answer": "found"},
        "is_final": True,
        "occurred_at": datetime.now(UTC).isoformat(),
    }
    assert (
        await client.post(f"/api/runs/{run_id}/tools/{tool.id}/results", json=result)
    ).status_code == 201
    body = {"exchange_id": later.id, "consumed_at": datetime.now(UTC).isoformat()}
    path = f"/api/runs/{run_id}/tool-results/{result['id']}/consumption"
    assert (await client.put(path, json=body)).status_code == 200
    assert (await client.put(path, json=body)).status_code == 200
    assert (await client.put(path, json={**body, "exchange_id": initial.id})).status_code == 409
    assert tool.exchange_id == initial.id
    assert (await database.get(ToolInvocationResult, result["id"])).consumed_exchange_id == later.id


async def test_revisited_node_and_interrupted_span(client, database, run_id):
    at = datetime.now(UTC)
    first = {
        "id": new_id(),
        "span_id": new_id(),
        "sequence": 1,
        "node_key": "greeting",
        "entered_at": at.isoformat(),
    }
    path = f"/api/runs/{run_id}/flow-visits"
    for _ in range(2):
        response = await client.post(path, json=first)
        assert response.status_code == 201, response.text
    end = {
        "exited_at": (at + timedelta(seconds=1)).isoformat(),
        "duration_ms": 999,
        "status": "interrupted",
    }
    assert (await client.put(f"{path}/{first['id']}/end", json=end)).status_code == 200
    assert (
        await client.put(f"{path}/{first['id']}/end", json={**end, "status": "completed"})
    ).status_code == 409
    second = {**first, "id": new_id(), "span_id": new_id(), "sequence": 2}
    assert (await client.post(path, json=second)).status_code == 201
    assert (
        await database.scalar(
            select(func.count()).select_from(FlowNodeVisit).where(FlowNodeVisit.run_id == run_id)
        )
        == 2
    )
    span = await database.get(TraceSpan, first["span_id"])
    assert span.status == "interrupted" and span.duration_ms == 999
    timeline = (await client.get(f"/api/runs/{run_id}/timeline")).json()
    assert len(timeline["flow_visits"]) == 2
    assert timeline["flow_visits"][1]["exited_at"] is None
