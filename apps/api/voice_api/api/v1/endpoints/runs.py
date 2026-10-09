"""Run requests and timeline inspection."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import AwareDatetime, BaseModel
from sqlalchemy import or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from voice_api.api.deps import get_session, require_legacy_owner
from voice_api.core.read_metrics import timed_read
from voice_api.core.security import allow_organization_member
from voice_api.models import (
    AgentVersion,
    Call,
    Contact,
    ConversationMessage,
    Exchange,
    Run,
    ToolInvocation,
    TraceSpan,
)
from voice_api.models.common import new_id
from voice_api.schemas.run_reads import RunPageResponse
from voice_api.schemas.timeline import TimelineResponse
from voice_api.services.evidence_service import related_evidence
from voice_api.services.read_pagination import decode_cursor, encode_cursor
from voice_api.services.resolution_service import resolve
from voice_api.services.runtime_recovery import recover_expired_assignments
from voice_shared.request_evidence import is_internal_span

router = APIRouter(tags=["runs"])
Session = Depends(get_session)
Operator = Depends(require_legacy_owner)


class BrowserRunRequest(BaseModel):
    channel: Literal["browser"] = "browser"
    agent_version_id: str
    contact_id: str | None = None
    logging_override: bool | None = None


@router.post("/runs", status_code=201)
async def request_browser_run(
    body: BrowserRunRequest, session: AsyncSession = Session, _: None = Operator
) -> dict:
    version = await session.get(AgentVersion, body.agent_version_id)
    if version is None or version.status != "published":
        raise HTTPException(422, "Run requires a published agent version")
    contact = await session.get(Contact, body.contact_id) if body.contact_id else None
    if body.contact_id and contact is None:
        raise HTTPException(422, "Contact not found")
    config, digest = await resolve(session, version, body.logging_override)
    run = Run(
        id=new_id(),
        channel="browser",
        agent_version_id=version.id,
        contact_id=body.contact_id,
        status="queued",
        resolved_config=config,
        config_hash=digest,
        snapshot_schema_version=1,
        contact_snapshot={}
        if contact is None
        else {
            "id": contact.id,
            "name": contact.name,
            "first_name": contact.first_name,
            "last_name": contact.last_name,
            "timezone": contact.timezone,
        },
    )
    session.add(run)
    await session.commit()
    return {"run_id": run.id, "status": run.status}


@router.get("/runs", response_model=RunPageResponse)
@allow_organization_member
@timed_read
async def list_runs(
    session: AsyncSession = Session,
    _: None = Operator,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    cursor: str | None = None,
    status: str | None = None,
    channel: Literal["phone", "browser"] | None = None,
    agent_version_id: str | None = None,
    created_after: AwareDatetime | None = None,
    created_before: AwareDatetime | None = None,
    search: Annotated[str | None, Query(max_length=120)] = None,
) -> dict:
    scope = session.sync_session.info.get("organization_scope_id")
    if not scope:
        raise HTTPException(403, "Organization access required")
    await recover_expired_assignments(session)
    filters = {
        "status": status,
        "channel": channel,
        "agent_version_id": agent_version_id,
        "created_after": created_after.isoformat() if created_after else None,
        "created_before": created_before.isoformat() if created_before else None,
        "search": search,
    }
    query = (
        select(
            Run.id,
            Run.channel,
            Run.transport_provider,
            Run.agent_version_id,
            Run.contact_id,
            Run.contact_snapshot["name"].as_string().label("contact_name"),
            Run.endpoint_id,
            Run.status,
            Run.created_at,
            Run.started_at,
            Run.ended_at,
            Run.resolved_config["call_limits"].label("call_limits"),
            Call.provider.label("call_provider"),
        )
        .outerjoin(Call, (Call.run_id == Run.id) & (Call.org_id == Run.org_id))
        .where(Run.org_id == scope, Run.channel != "text_test")
    )
    for value, column in (
        (status, Run.status),
        (channel, Run.channel),
        (agent_version_id, Run.agent_version_id),
    ):
        if value is not None:
            query = query.where(column == value)
    if created_after:
        query = query.where(Run.created_at >= created_after)
    if created_before:
        query = query.where(Run.created_at <= created_before)
    if search:
        escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = "%" + escaped + "%"
        query = query.where(
            or_(
                Run.id.ilike(pattern),
                Run.agent_version_id.ilike(pattern),
                Run.contact_snapshot["name"].as_string().ilike(pattern),
            )
        )
    if cursor:
        date, identity = decode_cursor(cursor, scope, filters)
        query = query.where(tuple_(Run.created_at, Run.id) < tuple_(date, identity))
    rows = (
        (
            await session.execute(
                query.order_by(Run.created_at.desc(), Run.id.desc()).limit(limit + 1)
            )
        )
        .mappings()
        .all()
    )
    more = len(rows) > limit
    page = rows[:limit]
    result = []
    for row in page:
        item = dict(row)
        fallback = item.pop("call_provider")
        item["transport_provider"] = (
            item["transport_provider"]
            or fallback
            or ("dashboard" if item["channel"] == "browser" else "sim7600")
        )
        result.append(item)
    return {
        "runs": result,
        "has_more": more,
        "next_cursor": encode_cursor(scope, filters, page[-1]["created_at"], page[-1]["id"])
        if more
        else None,
    }


@router.get("/runs/{run_id}")
@allow_organization_member
@timed_read
async def get_run(run_id: str, session: AsyncSession = Session, _: None = Operator) -> dict:
    await recover_expired_assignments(session, run_id)
    run = await session.get(Run, run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    call = await session.scalar(select(Call).where(Call.run_id == run_id))
    return {
        "id": run.id,
        "channel": run.channel,
        "transport_provider": run.transport_provider
        or (call.provider if call else ("dashboard" if run.channel == "browser" else "sim7600")),
        "agent_version_id": run.agent_version_id,
        "contact_id": run.contact_id,
        "endpoint_id": run.endpoint_id,
        "status": run.status,
        "config_hash": run.config_hash,
        "contact_snapshot": run.contact_snapshot,
        "resolved_config": run.resolved_config,
        "call_id": call.id if call else None,
        "created_at": run.created_at,
        "started_at": run.started_at,
        "ended_at": run.ended_at,
        "error": run.error,
    }


@router.get("/runs/{run_id}/timeline", response_model=TimelineResponse)
@allow_organization_member
@timed_read
async def timeline(
    run_id: str, session: AsyncSession = Session, _: None = Operator
) -> TimelineResponse:
    run = await session.get(Run, run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    call = await session.scalar(select(Call).where(Call.run_id == run_id))
    exchanges = (
        await session.scalars(
            select(Exchange).where(Exchange.run_id == run_id).order_by(Exchange.sequence)
        )
    ).all()
    ids = [x.id for x in exchanges]
    messages = (
        await session.scalars(
            select(ConversationMessage)
            .where(ConversationMessage.exchange_id.in_(ids))
            .order_by(ConversationMessage.created_at)
            if ids
            else select(ConversationMessage).where(False)
        )
    ).all()
    spans = (
        await session.scalars(
            select(TraceSpan).where(TraceSpan.run_id == run_id).order_by(TraceSpan.started_at)
        )
    ).all()
    spans = [span for span in spans if not is_internal_span(span)]
    tools = (
        await session.scalars(
            select(ToolInvocation)
            .where(ToolInvocation.run_id == run_id)
            .order_by(ToolInvocation.started_at)
        )
    ).all()
    return {
        **await related_evidence(session, run_id),
        "run": {
            "id": run.id,
            "status": run.status,
            "agent_id": (await session.get(AgentVersion, run.agent_version_id)).agent_id,
            "agent_version_id": run.agent_version_id,
            "evidence_complete": (
                not run.final_state["evidence_incomplete"]
                if isinstance(run.final_state, dict)
                and isinstance(run.final_state.get("evidence_incomplete"), bool)
                else None
            ),
        },
        "call": None
        if call is None
        else {
            "id": call.id,
            "status": call.status,
            "provider": call.provider,
            "provider_call_id": call.provider_call_id,
            "answered_at": call.answered_at,
            "ended_at": call.ended_at,
        },
        "exchanges": [
            {
                "id": x.id,
                "sequence": x.sequence,
                "origin": x.origin,
                "status": x.status,
                "created_at": x.created_at,
                "ended_at": x.ended_at,
            }
            for x in exchanges
        ],
        "messages": [
            {
                "id": x.id,
                "exchange_id": x.exchange_id,
                "role": x.role,
                "sequence": x.sequence,
                "content": x.content,
                "interrupted": x.interrupted,
                "created_at": x.created_at,
                "source_at": x.source_at,
                "playback_started_at": x.playback_started_at,
                "playback_ended_at": x.playback_ended_at,
            }
            for x in messages
        ],
        "spans": [
            {
                "id": x.id,
                "exchange_id": x.exchange_id,
                "parent_id": x.parent_id,
                "name": x.name,
                "category": x.category,
                "status": x.status,
                "output_state": x.output_state,
                "interruption_id": x.interruption_id,
                "started_at": x.started_at,
                "ended_at": x.ended_at,
                "attributes": x.attributes,
                "provider": x.provider,
                "model": x.model,
                "otel_trace_id": x.otel_trace_id,
                "otel_span_id": x.otel_span_id,
                "duration_ms": x.duration_ms,
                "ttfb_ms": x.ttfb_ms,
                "ttfa_ms": x.ttfa_ms,
                "ttfat_ms": x.ttfat_ms,
                "prompt_tokens": x.prompt_tokens,
                "completion_tokens": x.completion_tokens,
                "total_tokens": x.total_tokens,
                "cache_read_input_tokens": x.cache_read_input_tokens,
                "cache_creation_input_tokens": x.cache_creation_input_tokens,
                "reasoning_tokens": x.reasoning_tokens,
                "audio_seconds": x.audio_seconds,
                "input": x.input_payload,
                "output": x.output_payload,
            }
            for x in spans
        ],
        "tools": [
            {
                "id": x.id,
                "exchange_id": x.exchange_id,
                "llm_operation_id": x.llm_operation_id,
                "function_call_id": x.function_call_id,
                "binding_key": x.binding_key,
                "status": x.status,
                "interruption_id": x.interruption_id,
                "arguments": x.arguments,
                "result": x.result,
                "started_at": x.started_at,
                "ended_at": x.ended_at,
                "provider_message_id": x.provider_message_id,
                "receipts": [
                    {
                        "status": receipt.get("status", "unknown"),
                        "timestamp": receipt.get("timestamp"),
                        "recipient_id": receipt.get("recipient_id"),
                        "errors": receipt.get("errors", []),
                    }
                    for receipt in (x.receipts or [])
                    if isinstance(receipt, dict)
                ],
            }
            for x in tools
        ],
    }
