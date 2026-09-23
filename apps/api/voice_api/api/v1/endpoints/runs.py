"""Run requests and timeline inspection."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from voice_api.api.deps import get_session, require_operator
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
from voice_api.services.evidence_service import related_evidence
from voice_api.services.resolution_service import resolve

router = APIRouter(tags=["runs"])
Session = Depends(get_session)
Operator = Depends(require_operator)


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
            "timezone": contact.timezone,
        },
    )
    session.add(run)
    await session.commit()
@router.get("/runs")
async def list_runs(session: AsyncSession = Session, _: None = Operator) -> dict:
    rows = (await session.scalars(select(Run).order_by(Run.created_at.desc()))).all()
    return {
        "runs": [
            {
                "id": r.id,
                "channel": r.channel,
                "agent_version_id": r.agent_version_id,
                "contact_id": r.contact_id,
                "endpoint_id": r.endpoint_id,
                "status": r.status,
                "created_at": r.created_at,
                "call_limits": r.resolved_config.get("call_limits") if r.resolved_config else None,
            }
            for r in rows
        ]
    }


@router.get("/runs/{run_id}")
async def get_run(run_id: str, session: AsyncSession = Session, _: None = Operator) -> dict:
    run = await session.get(Run, run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    call = await session.scalar(select(Call).where(Call.run_id == run_id))
    return {
        "id": run.id,
        "channel": run.channel,
        "agent_version_id": run.agent_version_id,
        "contact_id": run.contact_id,
        "endpoint_id": run.endpoint_id,
        "status": run.status,
        "config_hash": run.config_hash,
        "contact_snapshot": run.contact_snapshot,
        "resolved_config": run.resolved_config,
        "call_id": call.id if call else None,
        "created_at": run.created_at,
    }


@router.get("/runs/{run_id}/timeline")
async def timeline(run_id: str, session: AsyncSession = Session, _: None = Operator) -> dict:
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
    tools = (
        await session.scalars(
            select(ToolInvocation)
            .where(ToolInvocation.run_id == run_id)
            .order_by(ToolInvocation.started_at)
        )
    ).all()
    return {
        **await related_evidence(session, run_id),
        "run": {"id": run.id, "status": run.status},
        "call": None if call is None else {"id": call.id, "status": call.status},
        "exchanges": [
            {"id": x.id, "sequence": x.sequence, "origin": x.origin, "status": x.status}
            for x in exchanges
        ],
        "messages": [
            {
                "id": x.id,
                "exchange_id": x.exchange_id,
                "role": x.role,
                "content": x.content,
                "interrupted": x.interrupted,
                "created_at": x.created_at,
            }
            for x in messages
        ],
        "spans": [
            {
                "id": x.id,
                "exchange_id": x.exchange_id,
                "name": x.name,
                "category": x.category,
                "status": x.status,
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
                "binding_key": x.binding_key,
                "status": x.status,
                "arguments": x.arguments,
                "result": x.result,
            }
            for x in tools
        ],
    }
