"""Fenced service-only synchronization and API business tools; no Clerk requests."""

from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, update
from voice_api.api.deps import get_session
from voice_api.api.v1.endpoints.evidence import store_record
from voice_api.core.runtime_config import get_runtime_settings as get_settings
from voice_api.core.security import safe_evidence
from voice_api.db.tenant_scope import bind_run_organization
from voice_api.models import (
    BrowserSession,
    Call,
    Callback,
    CredentialLease,
    ProviderCredential,
    Run,
    RunContextEvent,
    RuntimeAssignment,
    RuntimeToolAttempt,
)
from voice_api.models.common import now
from voice_api.services.run_context_service import enqueue_context_event
from voice_runtime.contracts.evidence import EvidenceBatch
from voice_shared.contracts import RuntimeSync, ToolRequest, configuration_hash
from voice_shared.logging import child_spans, exception_event, redact


async def authenticate(request: Request):
    settings = get_settings()
    supplied = request.headers.get("X-Voice-Runtime-Token", "")
    if not any(
        value and secrets.compare_digest(supplied, value)
        for value in (settings.runtime_service_token, settings.runtime_service_token_previous)
    ):
        raise HTTPException(401, "Runtime service authentication required")


router = APIRouter(prefix="/runtime", tags=["runtime"], dependencies=[Depends(authenticate)])
Session = Depends(get_session)


async def authorize(session, body, *, cleanup=False):
    run_id = str(body.run_id)
    await bind_run_organization(session, run_id)
    await session.scalar(select(Call).where(Call.run_id == run_id).with_for_update())
    assignment = await session.get(
        RuntimeAssignment, run_id, with_for_update=True, populate_existing=True
    )
    run = await session.get(Run, run_id, with_for_update=True, populate_existing=True)
    if (
        not assignment
        or not run
        or assignment.org_id != run.org_id
        or assignment.generation != str(body.generation)
        or assignment.boot_id != str(body.boot_id)
        or assignment.expires_at <= now()
        or not secrets.compare_digest(
            assignment.grant_hash,
            hashlib.sha256(body.grant.get_secret_value().encode()).hexdigest(),
        )
    ):
        raise HTTPException(403, "Expired or stale runtime session grant")
    if not cleanup and assignment.state not in {"starting", "active", "stopping"}:
        raise HTTPException(409, "Runtime execution is no longer active")
    return assignment, run


async def credentials_live(session, run_id):
    rows = (
        await session.execute(
            select(CredentialLease, ProviderCredential)
            .join(ProviderCredential, ProviderCredential.id == CredentialLease.credential_id)
            .where(CredentialLease.run_id == run_id)
        )
    ).all()
    run = await session.get(Run, run_id)
    refs = run.resolved_config.get("_resolved", {}).get("credentials", {})
    expected = {ref["credential_id"] for ref in refs.values()}
    telephony = run.resolved_config.get("_resolved", {}).get("telephony_credential")
    if telephony:
        expected.add(telephony["credential_id"])
    if expected - {credential.id for _, credential in rows}:
        return False
    return bool(rows) and all(
        lease.revoked_at is None
        and lease.expires_at > now()
        and credential.status == "stored"
        and credential.deleted_at is None
        for lease, credential in rows
    )


@router.post("/sync")
async def sync(body: RuntimeSync, session=Session):
    assignment, run = await authorize(session, body, cleanup=True)
    batch = EvidenceBatch(records=body.records) if body.records else SimpleNamespace(records=[])
    if any(record.run_id != run.id for record in batch.records):
        raise HTTPException(422, "Evidence belongs to another run")
    for record in batch.records:
        await store_record(
            session, run.id, type(record).model_validate(safe_evidence(record.model_dump()))
        )
    context_accepted = 0
    for update_data in body.context_updates:
        if "enqueue" in update_data:
            data = update_data["enqueue"]
            event = await enqueue_context_event(
                session,
                run_id=run.id,
                dedupe_key=data["dedupe_key"],
                source=data["source"],
                payload=safe_evidence(data["payload"]),
                tool_invocation_id=data.get("tool_invocation_id"),
                source_reference=data.get("source_reference"),
                connection_id=data.get("connection_id"),
                provider_message_id=data.get("provider_message_id"),
                status=data["status"],
            )
            if event.id != data["id"]:
                event.id = data["id"]
        else:
            event = await session.get(RunContextEvent, update_data["id"])
            if event is None or event.run_id != run.id:
                raise HTTPException(422, "Context acknowledgement belongs to another run")
            state = update_data["status"]
            if state not in {"delivered", "consumed", "ended_before_delivery"}:
                raise HTTPException(422, "Invalid context state")
            if event.status != "consumed":
                event.status = state
                if state == "delivered":
                    event.delivered_at = now()
                    event.context_message_index = update_data.get("context_message_index")
                if state == "consumed":
                    from voice_api.models import Exchange, TraceSpan

                    exchange = await session.get(Exchange, update_data.get("exchange_id"))
                    span = await session.get(TraceSpan, update_data.get("operation_id"))
                    if (
                        not exchange
                        or exchange.run_id != run.id
                        or not span
                        or span.run_id != run.id
                    ):
                        event.status = "delivered"
                    break
                    event.consumed_at = now()
                    event.consumed_exchange_id = exchange.id
                    event.consuming_span_id = span.id
        context_accepted += 1
    if body.diagnostics:
        if body.diagnostic_sequence > assignment.diagnostic_sequence + 1:
            raise HTTPException(409, "Diagnostic batch gap")
        if body.diagnostic_sequence == assignment.diagnostic_sequence + 1:
            path = (
                Path(get_settings().recordings_dir)
                / run.id
                / "runtime-diagnostics"
                / f"{body.diagnostic_sequence:08d}.jsonl"
            )
            data = "".join(
                json.dumps(redact(event), separators=(",", ":")) + "\n"
                for event in body.diagnostics
            )

            def write():
                import os

                path.parent.mkdir(parents=True, exist_ok=True)
                temp = path.with_suffix(".tmp")
                with temp.open("w", encoding="utf-8") as f:
                    f.write(data)
                    f.flush()
                    os.fsync(f.fileno())
                temp.replace(path)

            await asyncio.to_thread(write)
            assignment.diagnostic_sequence = body.diagnostic_sequence
    active = assignment.state in {"starting", "active"} and run.status in {
        "queued",
        "claimed",
        "running",
    }
    renewed = (
        active and assignment.lease_expires_at > now() and await credentials_live(session, run.id)
    )
    if renewed:
        assignment.lease_expires_at = now() + timedelta(seconds=30)
        run.lease_expires_at = assignment.lease_expires_at
    if body.metrics:
        assignment.metrics = redact(body.metrics)
    lifecycle = body.lifecycle or {}
    call = await session.scalar(select(Call).where(Call.run_id == run.id))
    if lifecycle.get("provider_call_id") and call:
        if call.provider_call_id not in {None, lifecycle["provider_call_id"]}:
            raise HTTPException(409, "Provider call identity mismatch")
        call.provider_call_id = lifecycle["provider_call_id"]
    if lifecycle.get("runtime_state") == "running" and active:
        run.status = "running"
        run.started_at = run.started_at or now()
        browser = await session.scalar(
            select(BrowserSession).where(BrowserSession.run_id == run.id)
        )
        if browser:
            browser.status = "connected"
            browser.connected_at = browser.connected_at or now()
    if lifecycle.get("termination"):
        from voice_runtime.execution.termination import TerminationSummary

        termination = TerminationSummary.model_validate(lifecycle["termination"])
        execution_status = (
            "cancelled" if termination.cause == "cancelled" else termination.execution_status
        )
        if run.status in {"queued", "claimed", "running", "uncertain"}:
            run.status = (
                execution_status if termination.cleanup_status == "confirmed" else "uncertain"
            )
            run.ended_at = (
                (run.ended_at or now()) if termination.cleanup_status == "confirmed" else None
            )
            run.error = (
                None
                if run.status in {"completed", "cancelled"}
                else "Call cleanup is unconfirmed; verify transport release before reuse"
                if run.status == "uncertain"
                else f"Call ended: {termination.cause.replace('_', ' ')}"
            )
        run.final_state = safe_evidence({**(run.final_state or {}), **lifecycle})
        assignment.state = "ended" if termination.cleanup_status == "confirmed" else "uncertain"
        browser = await session.scalar(
            select(BrowserSession).where(BrowserSession.run_id == run.id)
        )
        if browser:
            browser.status = "disconnected"
            browser.disconnected_at = browser.disconnected_at or now()
        if call and call.provider != "twilio" and termination.cleanup_status != "confirmed":
            call.status = "uncertain"
            call.ended_at = None
        if call and call.provider != "twilio" and termination.cleanup_status == "confirmed":
            call.status = execution_status
            call.ended_at = call.ended_at or now()
        if call and call.provider != "twilio":
            callback = await session.scalar(
                select(Callback).where(Callback.call_id == call.id).with_for_update()
            )
            if callback:
                callback.status = call.status
                if call.status == "completed":
                    callback.completed_at = call.ended_at
        await session.execute(
            update(RunContextEvent)
            .where(RunContextEvent.run_id == run.id, RunContextEvent.status == "pending")
            .values(status="ended_before_delivery")
        )
        renewed = False
    events = (
        await session.scalars(
            select(RunContextEvent)
            .where(RunContextEvent.run_id == run.id, RunContextEvent.status == "pending")
            .order_by(RunContextEvent.occurred_at)
            .limit(50)
        )
    ).all()
    text_accepted = 0
    if run.channel == "text_test":
        from voice_api.services.chat_service import persist_batch

        text_accepted = await persist_batch(
            session, run, body.text_records, body.text_checkpoint, lifecycle
        )
    elif body.text_records or body.text_checkpoint:
        raise HTTPException(422, "Text records require a text execution")
    await session.commit()
    return {
        "text_accepted": text_accepted,
        "accepted": len(batch.records),
        "context_accepted": context_accepted,
        "renewed": renewed,
        "stop": not renewed and not lifecycle.get("termination"),
        "context_events": [
            {"id": event.id, "status": "pending", "payload": event.payload} for event in events
        ],
    }


@router.post("/tools")
async def tool(body: ToolRequest, session=Session):
    assignment, run = await authorize(session, body)
    if (
        assignment.state == "stopping"
        or assignment.lease_expires_at <= now()
        or not await credentials_live(session, run.id)
    ):
        raise HTTPException(403, "Session credentials revoked")
    binding = run.resolved_config.get("_resolved", {}).get("tools", {}).get(body.name)
    if (
        not binding
        or binding["definition"].get("kind") != "registered"
        or body.name in {"end_call", "change_node", "classify_lead"}
    ):
        raise HTTPException(422, "Business tool absent from compiled session")
    import jsonschema

    try:
        jsonschema.validate(body.arguments, binding["definition"].get("parameters", {}))
    except jsonschema.ValidationError:
        raise HTTPException(422, "Tool arguments invalid") from None
    request_hash = configuration_hash({"name": body.name, "arguments": body.arguments})
    invocation_id = str(body.invocation_id)
    previous = await session.get(RuntimeToolAttempt, invocation_id)
    if previous:
        if previous.run_id != run.id or previous.request_hash != request_hash:
            raise HTTPException(409, "Tool operation identity conflict")
        return {
            "result": previous.result
            or {
                "status": "uncertain",
                "message": "Previous tool attempt unconfirmed; do not retry.",
            }
        }
    attempt = RuntimeToolAttempt(
        invocation_id=invocation_id,
        run_id=run.id,
        request_hash=request_hash,
        state="started",
        result=None,
    )
    session.add(attempt)
    await session.commit()
    from voice_api.services.runtime_tools import BackendToolDispatch

    settings = get_settings().model_copy(update={"provider_stage_keys": {}})
    if binding["definition"].get("handler") == "query_knowledge_base":
        from voice_api.services.credential_service import credential_scope
        from voice_api.services.provider_credentials import decrypt_provider_key

        ref = run.resolved_config.get("_resolved", {}).get("credentials", {}).get("embedding")
        credential = await session.get(ProviderCredential, ref["credential_id"]) if ref else None
        if (
            not credential
            or credential.provider != "gemini"
            or credential.version != ref["version"]
            or credential.status != "stored"
        ):
            raise HTTPException(403, "Knowledge embedding credential unavailable")
        settings = settings.model_copy(
            update={
                "provider_stage_keys": {
                    "embedding": decrypt_provider_key(
                        "gemini",
                        credential.ciphertext,
                        credential.key_id,
                        scope=credential_scope(credential),
                    )
                }
            }
        )
    adapter = BackendToolDispatch()
    adapter.run_id = run.id
    adapter._snapshot = run.resolved_config
    adapter.settings = settings
    from voice_shared.request_evidence import operation as request_operation
    from voice_shared.request_evidence import sink as request_sink

    request_events = []
    sink_token = request_sink.set(request_events.append)
    operation_token = request_operation.set(None)
    try:
        async with asyncio.timeout(14):
            result = await adapter._handler(body.name)(
                body.arguments, SimpleNamespace(active_tool_invocation_id=invocation_id)
            )
    except Exception as exc:
        exception_event("voice-api", exc)
        result = {
            "status": "uncertain",
            "message": "Business operation unconfirmed; do not retry automatically.",
        }
    finally:
        request_sink.reset(sink_token)
        request_operation.reset(operation_token)
    # Metadata from backend HTTP adapters is durable run evidence too. External
    # actions are never repeated if this persistence step fails.
    from voice_api.api.v1.endpoints.evidence import store_record
    from voice_api.models import ToolInvocation
    from voice_runtime.contracts.evidence import OperationEnded, OperationStarted

    invocation = await session.get(ToolInvocation, invocation_id)
    for event in request_events:
        fields = {
            "id": event["operation_id"],
            "run_id": run.id,
            "timestamp_ns": event["started_ns"],
            "operation_id": event["operation_id"],
            "name": "Backend API request",
            "category": "http_request",
            "provider": event["service"],
            "started_ns": event["started_ns"],
            "exchange_id": invocation.exchange_id if invocation else None,
            "attributes": {
                key: event[key]
                for key in ("method", "endpoint", "http_status", "error_type", "timing_scope")
                if event.get(key) is not None
            },
        }
        fields["attributes"]["tool_invocation_id"] = invocation_id
        if event["phase"] == "started":
            record = OperationStarted(kind="operation_started", **fields)
        else:
            record = OperationEnded(
                kind="span",
                **fields,
                ended_ns=event["ended_ns"],
                status=event["status"],
                duration_ms=event["duration_ms"],
                output_state="not_recorded",
            )
        await store_record(session, run.id, record)
    attempt.result = safe_evidence(result)
    attempt.state = "finished"
    await session.commit()
    return {"result": attempt.result, "debug_trace": child_spans.get() or []}
