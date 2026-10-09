"""Compact, nonduplicating execution maps and explicitly selected payload reads."""

import json
from datetime import datetime
from hashlib import sha256

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from voice_shared.request_evidence import is_internal_span

from voice_api.core.security import safe_evidence
from voice_api.models import (
    ConversationMessage,
    Exchange,
    FlowNodeVisit,
    Run,
    RunDiagnostic,
    ToolInvocation,
    TraceSpan,
)


async def require_run(session, run_id):
    row = await session.get(Run, run_id)
    if row is None:
        raise HTTPException(404, "Run not found")
    return row


async def rows(session, model, run_id, order):
    return (
        await session.scalars(select(model).where(model.run_id == run_id).order_by(order, model.id))
    ).all()


def offset(value: datetime | None, origin: datetime):
    return round((value - origin).total_seconds() * 1000, 1) if value else None


def compact(value):
    """Omit absent fields, keeping false/zero values meaningful."""
    return {key: item for key, item in value.items() if item is not None}


def bounded(value, after=0, max_chars=32000, expected_hash=None):
    encoded = json.dumps(jsonable_encoder(value), ensure_ascii=False, separators=(",", ":"))
    checksum = sha256(encoded.encode()).hexdigest()
    if expected_hash and expected_hash != checksum:
        raise HTTPException(409, "Evidence changed; refetch from offset zero")
    if after == 0 and len(encoded) <= max_chars:
        return value
    if after > len(encoded):
        raise HTTPException(422, "Chunk offset exceeds response size")
    end = min(after + max_chars, len(encoded))
    return {
        "chunked": True,
        "sha256": checksum,
        "total_chars": len(encoded),
        "offset": after,
        "text": encoded[after:end],
        "next_offset": end if end < len(encoded) else None,
        "continuation": "Call the same tool with after=next_offset and expected_hash=sha256; concatenate text chunks",
    }


def operation(row, origin, providers):
    identity = (row.provider, row.model)
    if identity not in providers:
        providers[identity] = f"p{len(providers) + 1}"
    metrics = compact(
        {
            name: getattr(row, name)
            for name in (
                "ttfb_ms",
                "ttfa_ms",
                "ttfat_ms",
                "prompt_tokens",
                "completion_tokens",
                "total_tokens",
                "cache_read_input_tokens",
                "cache_creation_input_tokens",
                "reasoning_tokens",
                "audio_seconds",
            )
        }
    )
    return compact(
        {
            "id": row.id,
            "parent_id": row.parent_id,
            "exchange_id": row.exchange_id,
            "category": row.category,
            "name": row.name,
            "status": row.status,
            "provider_ref": providers[identity],
            "start_ms": offset(row.started_at, origin),
            "end_ms": offset(row.ended_at, origin),
            "duration_ms": row.duration_ms,
            "output_state": row.output_state,
            "interruption_id": row.interruption_id,
            "metrics": metrics or None,
            "input_available": row.input_payload is not None,
            "output_available": row.output_payload is not None,
            "node_visit_id": row.attributes.get("node_visit_id"),
            "tool_invocation_id": row.attributes.get("tool_invocation_id"),
        }
    )


async def inspect(session, run_id):
    run = await require_run(session, run_id)
    origin = run.started_at or run.created_at
    messages = await rows(session, ConversationMessage, run_id, ConversationMessage.created_at)
    exchanges = await rows(session, Exchange, run_id, Exchange.sequence)
    spans = await rows(session, TraceSpan, run_id, TraceSpan.started_at)
    spans = [span for span in spans if not is_internal_span(span)]
    visits = await rows(session, FlowNodeVisit, run_id, FlowNodeVisit.sequence)
    tools = await rows(session, ToolInvocation, run_id, ToolInvocation.started_at)
    diagnostics = await rows(session, RunDiagnostic, run_id, RunDiagnostic.occurred_at)
    providers = {}
    indexed = {row.id: row for row in spans}
    ops, requests = [], []
    for row in spans:
        record = operation(row, origin, providers)
        if row.category in {"http_request", "provider_connection"}:
            record.update(
                compact(
                    {
                        key: row.attributes.get(key)
                        for key in (
                            "method",
                            "endpoint",
                            "http_status",
                            "error_type",
                            "timing_scope",
                            "attempt",
                        )
                    }
                )
            )
            requests.append(record)
        else:
            ops.append(record)
    transcript = [
        compact(
            {
                "id": row.id,
                "exchange_id": row.exchange_id,
                "sequence": row.sequence,
                "role": row.role,
                "text": row.content,
                "at_ms": offset(row.source_at or row.created_at, origin),
                "interrupted": row.interrupted,
                "playback_start_ms": offset(row.playback_started_at, origin),
                "playback_end_ms": offset(row.playback_ended_at, origin),
            }
        )
        for row in messages
    ]
    problems = [
        compact(
            {
                "id": row.id,
                "at_ms": offset(row.occurred_at, origin),
                "severity": row.severity,
                "source": row.source,
                "category": row.category,
                "code": row.code,
                "message": row.message,
                "http_status": row.http_status,
                "uncertain": row.uncertain,
                "operation_id": row.metadata_json.get("operation_id"),
                "request_id": row.metadata_json.get("request_id"),
                "detail_available": row.detail is not None,
            }
        )
        for row in diagnostics
        if row.severity in {"warning", "error"}
    ]
    # A failed operation can lack a normalized diagnostic; preserve that fact once.
    linked = {p.get("operation_id") for p in problems}
    for row in spans:
        if row.status == "failed" and row.id not in linked:
            problems.append(
                {
                    "id": row.id,
                    "operation_id": row.id,
                    "severity": "error",
                    "message": "Operation failed; inspect its recorded error/output",
                }
            )
    findings = [
        {
            "kind": "longest_operations",
            "operation_ids": [
                row.id
                for row in sorted(
                    [
                        s
                        for s in spans
                        if s.category not in {"http_request", "flow_node"}
                        and s.duration_ms is not None
                    ],
                    key=lambda s: s.duration_ms,
                    reverse=True,
                )[:5]
            ],
            "interpretation": "Elapsed duration, including overlap; not proof of root cause",
        }
    ]
    return jsonable_encoder(
        {
            "schema_version": 1,
            "time_origin": origin,
            "time_unit": "ms",
            "run": compact(
                {
                    "id": run.id,
                    "status": run.status,
                    "channel": run.channel,
                    "transport": run.transport_provider,
                    "agent_version_id": run.agent_version_id,
                    "config_hash": run.config_hash,
                    "end_ms": offset(run.ended_at, origin),
                    "error": safe_evidence(run.error),
                }
            ),
            "providers": {
                ref: compact({"provider": identity[0], "model": identity[1]})
                for identity, ref in providers.items()
            },
            "transcript": transcript,
            "exchanges": [
                compact(
                    {
                        "id": row.id,
                        "sequence": row.sequence,
                        "origin": row.origin,
                        "status": row.status,
                        "start_ms": offset(row.created_at, origin),
                        "end_ms": offset(row.ended_at, origin),
                    }
                )
                for row in exchanges
            ],
            "node_visits": [
                compact(
                    {
                        "id": row.id,
                        "sequence": row.sequence,
                        "node_key": row.node_key,
                        "span_id": row.span_id,
                        "trigger_tool_id": row.triggered_by_tool_id,
                    }
                )
                for row in visits
            ],
            "operations": ops,
            "api_attempts": requests,
            "tools": [
                compact(
                    {
                        "id": row.id,
                        "name": row.binding_key,
                        "status": row.status,
                        "exchange_id": row.exchange_id,
                        "llm_operation_id": row.llm_operation_id,
                        "start_ms": offset(row.started_at, origin),
                        "end_ms": offset(row.ended_at, origin),
                        "input_available": row.arguments is not None,
                        "output_available": row.result is not None,
                    }
                )
                for row in tools
            ],
            "problems": problems,
            "findings": findings,
            "coverage": {
                "overview_complete": True,
                "evidence_complete": None
                if not isinstance((run.final_state or {}).get("evidence_incomplete"), bool)
                else not run.final_state["evidence_incomplete"],
                "request_capture": "recorded_attempts_only",
                "request_capture_note": "Legacy and uninstrumented SDK connections may be absent; zero attempts does not prove zero requests",
                "unlinked_operation_ids": [
                    row.id
                    for row in spans
                    if not row.parent_id and row.id not in {v.span_id for v in visits}
                ],
                "unknown_parent_ids": sorted(
                    {
                        row.parent_id
                        for row in spans
                        if row.parent_id and row.parent_id not in indexed
                    }
                ),
            },
            "next": {
                "payloads": "inspect_operations",
                "logs": "read_run_logs",
                "config": "get_run_config",
            },
        }
    )


def payload(value):
    from voice_runtime.execution.redaction import redact

    value = redact(value)
    return (
        {"state": "recorded", "data": safe_evidence(value)}
        if value is not None
        else {"state": "not_recorded"}
    )


async def details(session, run_id, ids, sections, materialize_context=False):
    run = await require_run(session, run_id)
    result = {}
    providers = {}
    for identity in ids:
        span = await session.scalar(
            select(TraceSpan).where(TraceSpan.run_id == run_id, TraceSpan.id == identity)
        )
        tool = (
            None
            if span
            else await session.scalar(
                select(ToolInvocation).where(
                    ToolInvocation.run_id == run_id, ToolInvocation.id == identity
                )
            )
        )
        diagnostic = (
            None
            if span or tool
            else await session.scalar(
                select(RunDiagnostic).where(
                    RunDiagnostic.run_id == run_id, RunDiagnostic.id == identity
                )
            )
        )
        visit = (
            None
            if span or tool or diagnostic
            else await session.scalar(
                select(FlowNodeVisit).where(
                    FlowNodeVisit.run_id == run_id, FlowNodeVisit.id == identity
                )
            )
        )
        if visit:
            nodes = (run.resolved_config or {}).get("flow", {}).get("nodes", [])
            node = next((node for node in nodes if node.get("id") == visit.node_key), None)
            children = (
                await session.scalars(
                    select(TraceSpan)
                    .where(
                        TraceSpan.run_id == run_id,
                        TraceSpan.attributes["node_visit_id"].astext == visit.id,
                    )
                    .order_by(TraceSpan.started_at, TraceSpan.id)
                )
            ).all()
            result[identity] = {
                "node_key": visit.node_key,
                "sequence": visit.sequence,
                "span_id": visit.span_id,
                "operation_ids": [child.id for child in children],
            }
            if "input" in sections or "context" in sections:
                result[identity]["node_config"] = payload(node)
            continue
        if not span and not tool and not diagnostic:
            raise HTTPException(404, "Requested evidence not found in run")
        entry = {}
        if "input" in sections:
            if span:
                data = span.input_payload
                # Full context is a separately requested section even for an LLM input read.
                if span.category in {"llm", "classifier", "summarizer", "http_request"}:
                    data = (
                        {
                            key: value
                            for key, value in (data or {}).items()
                            if key
                            not in {
                                "messages",
                                "context",
                                "prompt",
                                "system_prompt",
                                "system_instruction",
                            }
                        }
                        if isinstance(data, dict)
                        else None
                    )
                entry["input"] = payload(data)
            elif tool:
                entry["input"] = payload(tool.arguments)
        if "output" in sections:
            entry["output"] = payload(
                span.output_payload if span else tool.result if tool else None
            )
        if "context" in sections:
            entry["context"] = payload(span.input_payload if span else None)
        if "error" in sections:
            entry["error"] = payload(
                {
                    "message": diagnostic.message,
                    "detail": diagnostic.detail,
                    "code": diagnostic.code,
                    "http_status": diagnostic.http_status,
                }
                if diagnostic
                else {"status": span.status if span else tool.status}
            )
        if "metrics" in sections and span:
            entry["metrics"] = operation(span, run.started_at or run.created_at, providers)
        if "related_events" in sections:
            ds = (
                await session.scalars(select(RunDiagnostic).where(RunDiagnostic.run_id == run_id))
            ).all()
            entry["related_events"] = [
                {"id": d.id, "message": d.message, "severity": d.severity}
                for d in ds
                if identity
                in {d.metadata_json.get("operation_id"), d.metadata_json.get("request_id")}
            ]
        result[identity] = entry
    # Batch-local content addressing avoids repeating identical full contexts.
    contents, seen = {}, {}
    messages = (
        await rows(session, ConversationMessage, run_id, ConversationMessage.created_at)
        if "context" in sections and not materialize_context
        else []
    )
    transcript = {}
    for message in messages:
        transcript.setdefault((message.role, message.content), []).append(message.id)
    for entry in result.values():
        context = entry.get("context")
        if context and context["state"] == "recorded" and not materialize_context:
            if isinstance(context["data"], dict) and isinstance(
                context["data"].get("messages"), list
            ):
                transformed = []
                for message in context["data"]["messages"]:
                    matches = (
                        transcript.get((message.get("role"), message.get("content")), [])
                        if isinstance(message, dict) and isinstance(message.get("content"), str)
                        else []
                    )
                    if len(matches) == 1 and set(message) <= {"role", "content"}:
                        transformed.append({"message_ref": matches[0]})
                    else:
                        canonical_message = json.dumps(
                            message, sort_keys=True, separators=(",", ":")
                        )
                        if canonical_message not in seen:
                            ref = f"c{len(seen) + 1}"
                            seen[canonical_message] = ref
                            contents[ref] = message
                        transformed.append({"content_ref": seen[canonical_message]})
                context["data"] = {**context["data"], "messages": transformed}
            canonical = json.dumps(context["data"], sort_keys=True, separators=(",", ":"))
            if canonical not in seen:
                ref = f"c{len(seen) + 1}"
                seen[canonical] = ref
                contents[ref] = context["data"]
            entry["context"] = {"state": "recorded", "content_ref": seen[canonical]}
    return {
        "operations": result,
        "contents": contents,
        "providers": {
            ref: compact({"provider": identity[0], "model": identity[1]})
            for identity, ref in providers.items()
        },
    }
