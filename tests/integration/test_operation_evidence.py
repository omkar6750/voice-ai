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


async def test_context_delivery_links_result_to_consuming_span(client, database, run_id, tool):
    at = datetime.now(UTC)
    exchange = Exchange(id=new_id(), run_id=run_id, sequence=1, origin="caller")
    database.add(exchange)
    await database.flush()
    tool.exchange_id = exchange.id
    await database.flush()
    result = {
        "id": new_id(),
        "sequence": 1,
        "payload": {"status": "ok"},
        "is_final": True,
        "occurred_at": at.isoformat(),
    }
    assert (
        await client.post(f"/api/runs/{run_id}/tools/{tool.id}/results", json=result)
    ).status_code == 201
    operation_id = new_id()
    delivery = {
        "id": new_id(),
        "run_id": run_id,
        "timestamp_ns": int((at + timedelta(milliseconds=1)).timestamp() * 1_000_000_000),
        "kind": "tool_result_context_updated",
        "delivery_id": new_id(),
        "invocation_id": tool.id,
        "result_id": result["id"],
        "is_final": True,
        "context_message_index": 4,
    }
    delivery["id"] = delivery["delivery_id"]
    operation = {
        "id": new_id(),
        "run_id": run_id,
        "timestamp_ns": int((at + timedelta(milliseconds=2)).timestamp() * 1_000_000_000),
        "kind": "operation_started",
        "operation_id": operation_id,
        "name": "inference",
        "category": "llm",
        "started_ns": int((at + timedelta(milliseconds=2)).timestamp() * 1_000_000_000),
    }
    ended = {
        **operation,
        "id": new_id(),
        "kind": "span",
        "ended_ns": int((at + timedelta(milliseconds=20)).timestamp() * 1_000_000_000),
        "duration_ms": 18,
        "status": "completed",
        "output_payload": {"text": "done"},
    }
    consumed = {
        "id": new_id(),
        "run_id": run_id,
        "timestamp_ns": int((at + timedelta(milliseconds=21)).timestamp() * 1_000_000_000),
        "kind": "tool_result_consumed",
        "result_id": result["id"],
        "exchange_id": exchange.id,
        "invocation_id": tool.id,
        "consuming_operation_id": operation_id,
    }
    response = await client.post(
        f"/api/runs/{run_id}/evidence",
        json={"records": [delivery, operation, ended, consumed]},
    )
    assert response.status_code == 200, response.text
    timeline = (await client.get(f"/api/runs/{run_id}/timeline")).json()
    assert timeline["tool_context_deliveries"] == [
        {
            "id": delivery["delivery_id"],
            "run_id": run_id,
            "tool_invocation_id": tool.id,
            "result_id": result["id"],
            "function_call_id": None,
            "is_final": True,
            "status": "consumed",
            "context_message_index": 4,
            "delivered_at": timeline["tool_context_deliveries"][0]["delivered_at"],
            "consumed_at": timeline["tool_context_deliveries"][0]["consumed_at"],
            "consumed_exchange_id": exchange.id,
            "consuming_span_id": operation_id,
        }
    ]


async def test_classifier_entry_result_reaches_following_llm(client, database, run_id):
    at = datetime.now(UTC)
    exchange = Exchange(id=new_id(), run_id=run_id, sequence=1, origin="greeting")
    database.add(exchange)
    await database.flush()
    classifier_operation_id = new_id()
    classifier_result_id = new_id()
    delivery_id = new_id()
    consuming_operation_id = new_id()
    def ns(value):
        return int(value.timestamp() * 1_000_000_000)
    classifier_start = {
        "id": new_id(),
        "run_id": run_id,
        "timestamp_ns": ns(at),
        "kind": "operation_started",
        "operation_id": classifier_operation_id,
        "exchange_id": exchange.id,
        "name": "classifier",
        "category": "classifier",
        "started_ns": ns(at),
        "provider": "groq",
        "model": "classifier-model",
        "attributes": {"phase": "entry", "node_key": "greeting"},
    }
    classifier_end = {
        **classifier_start,
        "id": new_id(),
        "kind": "span",
        "ended_ns": ns(at + timedelta(milliseconds=10)),
        "duration_ms": 10,
        "status": "completed",
        "output_payload": {"lead_temperature": "warm"},
    }
    classifier_result = {
        "id": classifier_result_id,
        "run_id": run_id,
        "timestamp_ns": ns(at + timedelta(milliseconds=11)),
        "kind": "classifier_result",
        "result_id": classifier_result_id,
        "operation_id": classifier_operation_id,
        "phase": "entry",
        "node_key": "greeting",
        "classifier_type": "llm",
        "status": "completed",
        "result": {"lead_temperature": "warm"},
        "transcript_sha256": "0" * 64,
    }
    delivery = {
        "id": delivery_id,
        "run_id": run_id,
        "timestamp_ns": ns(at + timedelta(milliseconds=12)),
        "kind": "classifier_context_updated",
        "delivery_id": delivery_id,
        "result_id": classifier_result_id,
        "operation_id": classifier_operation_id,
        "phase": "entry",
        "node_key": "greeting",
        "context_message_index": 2,
    }
    llm_start = {
        "id": new_id(),
        "run_id": run_id,
        "timestamp_ns": ns(at + timedelta(milliseconds=13)),
        "kind": "operation_started",
        "operation_id": consuming_operation_id,
        "exchange_id": exchange.id,
        "name": "inference",
        "category": "llm",
        "started_ns": ns(at + timedelta(milliseconds=13)),
    }
    llm_end = {
        **llm_start,
        "id": new_id(),
        "kind": "span",
        "ended_ns": ns(at + timedelta(milliseconds=20)),
        "duration_ms": 7,
        "status": "completed",
        "output_payload": {"text": "Hello"},
    }
    consumed = {
        "id": new_id(),
        "run_id": run_id,
        "timestamp_ns": ns(at + timedelta(milliseconds=21)),
        "kind": "classifier_result_consumed",
        "result_id": classifier_result_id,
        "exchange_id": exchange.id,
        "consuming_operation_id": consuming_operation_id,
    }
    response = await client.post(
        f"/api/runs/{run_id}/evidence",
        json={"records": [classifier_start, classifier_end, classifier_result, delivery, llm_start, llm_end, consumed]},
    )
    assert response.status_code == 200, response.text
    timeline = (await client.get(f"/api/runs/{run_id}/timeline")).json()
    assert timeline["classifier_results"][0]["status"] == "completed"
    assert timeline["classifier_context_deliveries"][0]["status"] == "consumed"
    assert timeline["classifier_context_deliveries"][0]["consuming_operation_id"] == consuming_operation_id


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


async def test_interruption_evidence_links_cancelled_spans_and_appears_in_timeline(
    client, database, run_id
):
    at = datetime.now(UTC)
    exchange = Exchange(id=new_id(), run_id=run_id, sequence=1, origin="caller")
    database.add(exchange)
    await database.flush()

    speech_id = new_id()
    llm_id = new_id()

    def ns(value):
        return int(value.timestamp() * 1_000_000_000)

    speech_start = {
        "id": new_id(),
        "run_id": run_id,
        "timestamp_ns": ns(at),
        "kind": "operation_started",
        "operation_id": speech_id,
        "exchange_id": exchange.id,
        "name": "caller speech",
        "category": "speech",
        "started_ns": ns(at),
    }
    llm_start = {
        "id": new_id(),
        "run_id": run_id,
        "timestamp_ns": ns(at + timedelta(milliseconds=1)),
        "kind": "operation_started",
        "operation_id": llm_id,
        "exchange_id": exchange.id,
        "name": "inference",
        "category": "llm",
        "started_ns": ns(at + timedelta(milliseconds=1)),
        "parent_id": speech_id,
    }
    interruption_id = new_id()
    interruption = {
        "id": interruption_id,
        "run_id": run_id,
        "timestamp_ns": ns(at + timedelta(milliseconds=5)),
        "kind": "interruption",
        "interruption_id": interruption_id,
        "exchange_id": exchange.id,
        "source": "caller",
        "reason": "caller_barge_in",
        "frame_type": "InterruptionFrame",
        "interrupted_operation_ids": [llm_id],
        "interrupted_tool_invocation_ids": [],
    }
    speech_end = {
        **speech_start,
        "id": new_id(),
        "kind": "span",
        "ended_ns": ns(at + timedelta(milliseconds=20)),
        "duration_ms": 20,
        "status": "completed",
        "output_state": "not_applicable",
    }
    llm_end = {
        **llm_start,
        "id": new_id(),
        "kind": "span",
        "ended_ns": ns(at + timedelta(milliseconds=6)),
        "duration_ms": 5,
        "status": "interrupted",
        "output_state": "interrupted",
        "interruption_id": interruption_id,
        "output_payload": {"text": "partial"},
    }

    response = await client.post(
        f"/api/runs/{run_id}/evidence",
        json={"records": [speech_start, llm_start, interruption, speech_end, llm_end]},
    )
    assert response.status_code == 200, response.text
    timeline = (await client.get(f"/api/runs/{run_id}/timeline")).json()
    assert timeline["interruptions"][0]["reason"] == "caller_barge_in"
    span = next(item for item in timeline["spans"] if item["id"] == llm_id)
    assert span["parent_id"] == speech_id
    assert span["output_state"] == "interrupted"
    assert span["interruption_id"] == interruption_id


async def test_diagnostic_evidence_preserves_provider_details_and_redacts_metadata(
    client, run_id
):
    at = datetime.now(UTC)
    diagnostic_id = new_id()
    record = {
        "id": diagnostic_id,
        "run_id": run_id,
        "timestamp_ns": int(at.timestamp() * 1_000_000_000),
        "kind": "diagnostic",
        "diagnostic_id": diagnostic_id,
        "severity": "error",
        "category": "provider_rate_limit",
        "source": "provider",
        "code": "provider_throttled",
        "message": "Provider throttled the request",
        "detail": "Retry after 12 seconds",
        "retryable": True,
        "uncertain": False,
        "provider_request_id": "req-123",
        "http_status": 429,
        "retry_after_seconds": 12,
        "metadata": {"provider": "groq", "secret": "should-not-survive"},
    }
    response = await client.post(
        f"/api/runs/{run_id}/evidence", json={"records": [record]}
    )
    assert response.status_code == 200, response.text
    timeline = (await client.get(f"/api/runs/{run_id}/timeline")).json()
    diagnostic = timeline["diagnostics"][0]
    assert diagnostic["category"] == "provider_rate_limit"
    assert diagnostic["http_status"] == 429
    assert diagnostic["retry_after_seconds"] == 12
    assert diagnostic["metadata"]["secret"] == "[REDACTED]"
