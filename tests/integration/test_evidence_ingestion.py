"""End-to-end finalized transcript capture through spool, HTTP, PostgreSQL and timeline."""

from datetime import UTC, datetime
from time import time_ns

import pytest
from sqlalchemy import func, select
from voice_api.models import (
    ClassifierContextDelivery,
    ClassifierResult,
    ConversationMessage,
    Exchange,
    FlowNodeVisit,
    InterruptionEvent,
    Run,
    RunDiagnostic,
    ToolContextDelivery,
    ToolInvocation,
    ToolInvocationResult,
    TraceSpan,
)
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


async def test_every_evidence_variant_maps_to_its_database_row(client, database):
    run_id = await browser_run(client)
    run = await database.get(Run, run_id)
    config = dict(run.resolved_config)
    config["_resolved"] = {
        "tools": {"send_message": {"version_id": "tool-v1", "definition": {}}}
    }
    run.resolved_config = config
    await database.commit()

    now_ns = time_ns()
    exchange_id, llm_id, consume_id = new_id(), new_id(), new_id()
    classifier_id, invocation_id, result_id = new_id(), new_id(), new_id()
    visit_id, flow_span_id = new_id(), new_id()
    classifier_result_id = new_id()

    def record(kind, **values):
        return {
            "id": new_id(),
            "run_id": run_id,
            "timestamp_ns": now_ns,
            "kind": kind,
            **values,
        }

    def operation(operation_id, name, category, status, index):
        start = now_ns + index * 1_000_000
        start_record = record(
            "operation_started",
            operation_id=operation_id,
            name=name,
            category=category,
            started_ns=start,
        )
        ended_record = {
            **start_record,
            "id": new_id(),
            "kind": "span",
            "timestamp_ns": start + 100_000_000,
            "ended_ns": start + 100_000_000,
            "duration_ms": 100,
            "status": status,
        }
        return start_record, ended_record

    llm_start, llm_end = operation(llm_id, "agent inference", "llm", "completed", 1)
    consume_start, consume_end = operation(
        consume_id, "tool follow-up", "llm", "completed", 2
    )
    classifier_start, classifier_end = operation(
        classifier_id, "entry classifier", "classifier", "completed", 3
    )
    records = [
        record("exchange", exchange_id=exchange_id, sequence=1, origin="greeting"),
        record(
            "flow_visit_started",
            visit_id=visit_id,
            span_id=flow_span_id,
            sequence=1,
            node_key="greeting",
            started_ns=now_ns,
        ),
        llm_start,
        llm_end,
        record(
            "tool_started",
            invocation_id=invocation_id,
            exchange_id=exchange_id,
            binding_key="send_message",
            tool_version_id="tool-v1",
            function_call_id="function-1",
            llm_operation_id=llm_id,
            arguments={},
            started_ns=now_ns + 10_000_000,
        ),
        record(
            "tool_result",
            id=result_id,
            invocation_id=invocation_id,
            sequence=1,
            payload={"status": "sent"},
            is_final=True,
        ),
        record(
            "tool_result_context_updated",
            delivery_id=new_id(),
            invocation_id=invocation_id,
            result_id=result_id,
            function_call_id="function-1",
            is_final=True,
            context_message_index=4,
        ),
        record(
            "tool_ended",
            invocation_id=invocation_id,
            ended_ns=now_ns + 20_000_000,
            status="completed",
            result={"status": "sent"},
        ),
        consume_start,
        consume_end,
        record(
            "tool_result_consumed",
            result_id=result_id,
            exchange_id=exchange_id,
            invocation_id=invocation_id,
            consuming_operation_id=consume_id,
        ),
        classifier_start,
        classifier_end,
        record(
            "classifier_result",
            result_id=classifier_result_id,
            operation_id=classifier_id,
            phase="entry",
            node_key="greeting",
            classifier_type="llm",
            status="completed",
            result={"lead_temperature": "warm"},
            transcript_sha256="a" * 64,
        ),
        record(
            "classifier_context_updated",
            delivery_id=new_id(),
            result_id=classifier_result_id,
            operation_id=classifier_id,
            phase="entry",
            node_key="greeting",
            context_message_index=5,
        ),
        record(
            "classifier_result_consumed",
            result_id=classifier_result_id,
            exchange_id=exchange_id,
            consuming_operation_id=consume_id,
        ),
        record(
            "interruption",
            interruption_id=new_id(),
            exchange_id=exchange_id,
            source="caller",
            reason="barge in",
            frame_type="InterruptionFrame",
        ),
        record(
            "diagnostic",
            diagnostic_id=new_id(),
            severity="warning",
            category="provider_warning",
            source="provider",
            message="Provider warning",
        ),
        record(
            "message",
            exchange_id=exchange_id,
            sequence=1,
            role="assistant",
            content="Hello",
            source_timestamp=datetime.now(UTC).isoformat(),
        ),
        record("exchange_ended", exchange_id=exchange_id, status="completed"),
        record(
            "flow_visit_ended",
            visit_id=visit_id,
            ended_ns=now_ns + 100_000_000,
            duration_ms=100,
            status="completed",
        ),
    ]
    # Exercise every discriminant through API parsing, storage, then idempotent replay.
    endpoint = f"/api/runs/{run_id}/evidence"
    body = {"records": records}
    for _ in range(2):
        response = await client.post(endpoint, json=body)
        assert response.status_code == 200, response.text
        assert response.json()["accepted"] == len(records)

    expected = {
        Exchange: 1,
        ConversationMessage: 1,
        TraceSpan: 4,
        FlowNodeVisit: 1,
        ToolInvocation: 1,
        ToolInvocationResult: 1,
        ToolContextDelivery: 1,
        ClassifierResult: 1,
        ClassifierContextDelivery: 1,
        InterruptionEvent: 1,
        RunDiagnostic: 1,
    }
    for model, count in expected.items():
        assert await database.scalar(
            select(func.count()).select_from(model).where(model.run_id == run_id)
        ) == count


async def test_invalid_record_is_rejected_before_spool_append(client, database, tmp_path):
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
        size_before = spool.path.stat().st_size
        with pytest.raises(ValueError):
            spool.submit(invalid)
        assert spool.path.stat().st_size == size_before
        persisted, _ = spool._read_batch(100)
        assert len(persisted) == 1
        assert persisted[0]["kind"] == "exchange"
        assert not spool.cursor_path.exists()
        assert (
            await database.scalar(
                select(func.count()).select_from(Exchange).where(Exchange.run_id == run_id)
            )
            == 0
        )
    finally:
        if spool.error:
            with pytest.raises(RuntimeError, match="durable evidence spool failed"):
                await spool.close()
        else:
            await spool.close()
