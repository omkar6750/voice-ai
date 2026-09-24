"""End-to-end finalized transcript capture through spool, HTTP, PostgreSQL and timeline."""

from datetime import UTC, datetime
from time import time_ns

import pytest
from sqlalchemy import func, select
from voice_api.models import ConversationMessage, Exchange, TraceSpan
from voice_api.models.common import new_id
from voice_runtime.execution.evidence_client import ApiEvidenceIngestor
from voice_runtime.execution.exchange import ExchangeTracker
from voice_runtime.execution.spool import DurableSpool


async def browser_run(client):
    config = {
        "name": "test",
        "flow": {"initial_node": "greeting", "nodes": [{"id": "greeting", "terminal": True}]},
    }
    agent = await client.post("/api/agents", json={"name": new_id(), "config": config})
    assert agent.status_code == 201, agent.text
    version = agent.json()["version_id"]
    assert (
        await client.post(f"/api/agent-versions/{version}/publish", json={"revision": 1})
    ).status_code == 200
    return (await client.post("/api/runs", json={"agent_version_id": version})).json()["run_id"]


async def test_typed_operation_metrics_and_replay(client, database):
    run_id = await browser_run(client)
    now = time_ns()
    record = {
        "kind": "operation_started",
        "id": new_id(),
        "run_id": run_id,
        "timestamp_ns": now,
        "operation_id": new_id(),
        "name": "greeting",
        "category": "llm",
        "started_ns": now,
        "provider": "groq",
        "model": "test-model",
        "otel_trace_id": "a" * 32,
        "otel_span_id": "b" * 16,
        "input_payload": {"messages": [{"role": "user", "content": "Hello"}]},
    }
    endpoint = f"/api/runs/{run_id}/evidence"
    assert (await client.post(endpoint, json={"records": [record]})).status_code == 200
    completed = {
        **record,
        "kind": "span",
        "id": new_id(),
        "ended_ns": now + 100000000,
        "duration_ms": 100,
        "status": "completed",
        "output_payload": {"text": "Hi", "api_key": "do-not-retain"},
        "ttfb_ms": 20,
        "prompt_tokens": 15,
        "completion_tokens": 2,
    }
    for _ in range(2):
        response = await client.post(endpoint, json={"records": [completed]})
        assert response.status_code == 200, response.text
    span = await database.get(TraceSpan, record["operation_id"])
    assert span.provider == "groq" and span.model == "test-model"
    assert span.otel_trace_id == "a" * 32
    assert span.ttfb_ms == 20 and span.prompt_tokens == 15
    assert span.reasoning_tokens is None and span.audio_seconds is None
    assert span.input_payload == record["input_payload"]
    assert "do-not-retain" not in str(span.output_payload)
    timeline = (await client.get(f"/api/runs/{run_id}/timeline")).json()
    assert timeline["spans"][0]["completion_tokens"] == 2
    assert timeline["spans"][0]["input"] == record["input_payload"]
    assert timeline["spans"][0]["provider"] == "groq"
    assert "do-not-retain" not in str(timeline["spans"][0]["output"])
    listed = (await client.get("/api/runs")).json()["runs"]
    assert listed[0]["id"] == run_id
    assert listed[0]["started_at"] is None
    invalid = {**completed, "prompt_tokens": -1}
    assert (await client.post(endpoint, json={"records": [invalid]})).status_code == 422
    conflict = {**completed, "completion_tokens": 3}
    assert (await client.post(endpoint, json={"records": [conflict]})).status_code == 409


async def test_spool_delivery_and_replay(client, database, tmp_path):
    run_id = await browser_run(client)
    spool = DurableSpool(tmp_path / "evidence.jsonl")
    try:
        tracker = ExchangeTracker(run_id, spool)
        tracker.assistant_started()
        operation = tracker.start_operation("response", "llm", model="test")
        tracker.finish_operation(operation, "completed", output="hello")
        tracker.assistant_message("Hello", datetime.now(UTC).isoformat(), interrupted=True)
        tracker.user_message("Wait", datetime.now(UTC).isoformat())
        await spool.flush()
        records, _ = spool._read_batch(100)
        ingestor = ApiEvidenceIngestor(client, run_id, "test-only")
        assert await spool.deliver_once(ingestor) == len(records)
        assert await spool.deliver_once(ingestor) == 0
        # Simulate API commit followed by lost client acknowledgement.
        await ingestor.ingest(records)
        assert (
            await database.scalar(
                select(func.count())
                .select_from(ConversationMessage)
                .where(ConversationMessage.run_id == run_id)
            )
            == 2
        )
        assert (
            await database.scalar(
                select(func.count()).select_from(TraceSpan).where(TraceSpan.run_id == run_id)
            )
            == 1
        )
        timeline = (await client.get(f"/api/runs/{run_id}/timeline")).json()
        assert timeline["messages"][0]["content"] == "Hello"
        assert timeline["messages"][0]["interrupted"] is True
        assert timeline["messages"][0]["sequence"] == 1
        assert "playback_started_at" in timeline["messages"][0]
        assert timeline["spans"][0]["duration_ms"] >= 0
    finally:
        await spool.close()


async def test_batch_failure_rolls_back_and_does_not_ack(client, database, tmp_path):
    run_id = await browser_run(client)
    spool = DurableSpool(tmp_path / "invalid.jsonl")
    try:
        tracker = ExchangeTracker(run_id, spool)
        tracker.begin("greeting")
        await spool.flush()
        records, _ = spool._read_batch(100)
        invalid = {
            "kind": "message",
            "id": new_id(),
            "run_id": run_id,
            "timestamp_ns": records[0]["timestamp_ns"],
            "exchange_id": new_id(),
            "sequence": 1,
            "role": "user",
            "content": "Missing exchange",
            "source_timestamp": datetime.now(UTC).isoformat(),
        }
        spool.submit(invalid)
        await spool.flush()
        with pytest.raises(RuntimeError, match="unacknowledged"):
            await spool.deliver_once(ApiEvidenceIngestor(client, run_id, "test-only"))
        assert not spool.cursor_path.exists()
        assert (
            await database.scalar(
                select(func.count()).select_from(Exchange).where(Exchange.run_id == run_id)
            )
            == 0
        )
    finally:
        await spool.close()
