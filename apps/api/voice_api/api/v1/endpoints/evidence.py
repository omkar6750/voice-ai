"""Durable flow visits, tool results, and streaming evidence ingestion."""

from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from voice_api.api.deps import get_session, require_operator
from voice_api.core.security import safe_evidence
from voice_api.models import (
    ConversationMessage,
    Exchange,
    FlowNodeVisit,
    Run,
    ToolInvocation,
    ToolInvocationResult,
    TraceSpan,
)
from voice_runtime.contracts.evidence import (
    EvidenceBatch,
    ExchangeRecord,
    MessageRecord,
    OperationEnded,
)

router = APIRouter(tags=["evidence"])
Session = Depends(get_session)
Operator = Depends(require_operator)
Id = Annotated[str, Field(min_length=1, max_length=36)]


class EvidenceBody(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VisitBody(EvidenceBody):
    id: Id
    span_id: Id
    sequence: int = Field(gt=0)
    node_key: str = Field(min_length=1, max_length=120)
    entered_at: AwareDatetime
    triggered_by_tool_id: Id | None = None


class VisitEnd(EvidenceBody):
    exited_at: AwareDatetime
    duration_ms: float = Field(ge=0, allow_inf_nan=False)
    status: Literal["completed", "interrupted", "failed"] = "completed"


class ResultBody(EvidenceBody):
    id: Id
    sequence: int = Field(gt=0)
    payload: JsonValue
    is_final: bool
    occurred_at: AwareDatetime


class ConsumptionBody(EvidenceBody):
    exchange_id: Id
    consumed_at: AwareDatetime


def at_ns(value: int) -> datetime:
    seconds, nanoseconds = divmod(value, 1000000000)
    return datetime(1970, 1, 1, tzinfo=UTC) + timedelta(
        seconds=seconds, microseconds=nanoseconds // 1000
    )


def verify_same(existing, fields: dict) -> None:
    if any(getattr(existing, key) != value for key, value in fields.items()):
        raise HTTPException(409, "Evidence identity conflicts with existing record")


async def store_record(session: AsyncSession, run_id: str, record) -> None:
    if isinstance(record, ExchangeRecord):
        fields = dict(
            run_id=run_id,
            sequence=record.sequence,
            origin=record.origin,
            created_at=at_ns(record.timestamp_ns),
        )
        row = await session.get(Exchange, record.exchange_id)
        if row:
            verify_same(row, fields)
        else:
            session.add(Exchange(id=record.exchange_id, **fields))
        await session.flush()
        return
    if record.exchange_id is not None:
        exchange = await session.get(Exchange, record.exchange_id)
        if exchange is None or exchange.run_id != run_id:
            raise HTTPException(422, "Evidence requires an existing exchange in this run")
    if isinstance(record, MessageRecord):
        fields = dict(
            run_id=run_id,
            exchange_id=record.exchange_id,
            sequence=record.sequence,
            role=record.role,
            content=record.content,
            source_at=record.source_timestamp,
            interrupted=record.interrupted,
            created_at=at_ns(record.timestamp_ns),
        )
        row = await session.get(ConversationMessage, record.id)
        if row:
            verify_same(row, fields)
        else:
            session.add(ConversationMessage(id=record.id, **fields))
    else:
        fields = dict(
            run_id=run_id,
            exchange_id=record.exchange_id,
            name=record.name,
            category=record.category,
            started_at=at_ns(record.started_ns),
            provider=record.provider,
            model=record.model,
            otel_trace_id=record.otel_trace_id,
            otel_span_id=record.otel_span_id,
            input_payload=record.input_payload,
        )
        row = await session.get(TraceSpan, record.operation_id)
        if row:
            verify_same(row, fields)
        else:
            row = TraceSpan(id=record.operation_id, **fields)
            session.add(row)
        if isinstance(record, OperationEnded):
            ended_at = at_ns(record.ended_ns)
            if ended_at < fields["started_at"]:
                raise HTTPException(422, "Operation end precedes start")
            completion = dict(
                ended_at=ended_at,
                duration_ms=record.duration_ms,
                status=record.status,
                attributes=record.attributes,
                output_payload=record.output_payload,
                ttfb_ms=record.ttfb_ms,
                ttfa_ms=record.ttfa_ms,
                ttfat_ms=record.ttfat_ms,
                prompt_tokens=record.prompt_tokens,
                completion_tokens=record.completion_tokens,
                reasoning_tokens=record.reasoning_tokens,
                audio_seconds=record.audio_seconds,
            )
            if row.ended_at is not None:
                verify_same(row, completion)
            else:
                for key, value in completion.items():
                    setattr(row, key, value)
        elif row.ended_at is None:
            if row.attributes is not None:
                verify_same(row, {"attributes": record.attributes})
            row.attributes = record.attributes
    await session.flush()


@router.post("/runs/{run_id}/evidence")
async def ingest(
    run_id: str, body: EvidenceBatch, session: AsyncSession = Session, _: None = Operator
) -> dict:
    if any(record.run_id != run_id for record in body.records):
        raise HTTPException(422, "Batch contains evidence for another run")
    # Serialize batches per run; retries see committed records before making changes.
    if await session.get(Run, run_id, with_for_update=True) is None:
        raise HTTPException(404, "Run not found")
    try:
        for record in body.records:
            record = type(record).model_validate(safe_evidence(record.model_dump()))
            await store_record(session, run_id, record)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(409, "Evidence conflicts with database ordering or ownership") from None
    except Exception:
        await session.rollback()
        raise
    return {"accepted": len(body.records)}


async def locked_run(session: AsyncSession, run_id: str) -> Run:
    run = await session.get(Run, run_id, with_for_update=True)
    if run is None:
        raise HTTPException(404, "Run not found")
    return run


@router.post("/runs/{run_id}/flow-visits", status_code=201)
async def enter_visit(
    run_id: str, body: VisitBody, session: AsyncSession = Session, _: None = Operator
) -> dict:
    run = await locked_run(session, run_id)
    existing = await session.get(FlowNodeVisit, body.id)
    if existing is not None:
        span = await session.get(TraceSpan, existing.span_id)
        if (
            existing.run_id,
            existing.span_id,
            existing.sequence,
            existing.node_key,
            existing.triggered_by_tool_id,
            span.started_at,
        ) != (
            run_id,
            body.span_id,
            body.sequence,
            body.node_key,
            body.triggered_by_tool_id,
            body.entered_at,
        ):
            raise HTTPException(409, "Visit ID was used for different evidence")
        return {"id": existing.id, "span_id": existing.span_id}
    nodes = run.resolved_config.get("flow", {}).get("nodes", [])
    if body.node_key not in {node["id"] for node in nodes}:
        raise HTTPException(422, "Node is absent from resolved flow configuration")
    if body.triggered_by_tool_id:
        tool = await session.get(ToolInvocation, body.triggered_by_tool_id)
        if tool is None or tool.run_id != run_id:
            raise HTTPException(422, "Triggering tool must belong to run")
    latest = await session.scalar(
        select(func.max(FlowNodeVisit.sequence)).where(FlowNodeVisit.run_id == run_id)
    )
    if body.sequence != (latest or 0) + 1:
        raise HTTPException(409, "Visit sequence must follow previous visit")
    if await session.get(TraceSpan, body.span_id) is not None:
        raise HTTPException(409, "Span ID is already used")
    session.add(
        TraceSpan(
            id=body.span_id,
            run_id=run_id,
            name=body.node_key,
            category="flow_node",
            started_at=body.entered_at,
            status="running",
        )
    )
    await session.flush()
    session.add(
        FlowNodeVisit(
            id=body.id,
            run_id=run_id,
            span_id=body.span_id,
            sequence=body.sequence,
            node_key=body.node_key,
            triggered_by_tool_id=body.triggered_by_tool_id,
        )
    )
    await session.commit()
    return {"id": body.id, "span_id": body.span_id}


@router.put("/runs/{run_id}/flow-visits/{visit_id}/end")
async def end_visit(
    run_id: str, visit_id: str, body: VisitEnd, session: AsyncSession = Session, _: None = Operator
) -> dict:
    await locked_run(session, run_id)
    visit = await session.get(FlowNodeVisit, visit_id)
    if visit is None or visit.run_id != run_id:
        raise HTTPException(404, "Visit not found")
    span = await session.get(TraceSpan, visit.span_id, with_for_update=True)
    if body.exited_at < span.started_at:
        raise HTTPException(422, "Exit precedes entry")
    if span.ended_at is not None and (span.ended_at, span.duration_ms, span.status) != (
        body.exited_at,
        body.duration_ms,
        body.status,
    ):
        raise HTTPException(409, "Visit already ended with different evidence")
    span.ended_at, span.duration_ms, span.status = body.exited_at, body.duration_ms, body.status
    await session.commit()
    return {"id": visit.id, "status": span.status}


@router.post("/runs/{run_id}/tools/{invocation_id}/results", status_code=201)
async def record_result(
    run_id: str,
    invocation_id: str,
    body: ResultBody,
    session: AsyncSession = Session,
    _: None = Operator,
) -> dict:
    body.payload = safe_evidence(body.payload)
    tool = await session.get(ToolInvocation, invocation_id, with_for_update=True)
    if tool is None or tool.run_id != run_id:
        raise HTTPException(404, "Tool invocation not found")
    existing = await session.get(ToolInvocationResult, body.id)
    if existing is not None:
        if (
            existing.run_id,
            existing.tool_invocation_id,
            existing.sequence,
            existing.payload,
            existing.is_final,
            existing.occurred_at,
        ) != (run_id, invocation_id, body.sequence, body.payload, body.is_final, body.occurred_at):
            raise HTTPException(409, "Result ID was used for different evidence")
        return {"id": existing.id, "is_final": existing.is_final}
    final = await session.scalar(
        select(ToolInvocationResult.id).where(
            ToolInvocationResult.tool_invocation_id == invocation_id, ToolInvocationResult.is_final
        )
    )
    latest = await session.scalar(
        select(func.max(ToolInvocationResult.sequence)).where(
            ToolInvocationResult.tool_invocation_id == invocation_id
        )
    )
    if final or body.sequence != (latest or 0) + 1:
        raise HTTPException(409, "Tool already finalized or result sequence is out of order")
    if body.occurred_at < tool.started_at:
        raise HTTPException(422, "Result precedes invocation")
    # Presence of a row establishes result existence even when payload is JSON null.
    session.add(
        ToolInvocationResult(run_id=run_id, tool_invocation_id=invocation_id, **body.model_dump())
    )
    # Execution outcome remains independent: a final result may describe a failure.
    await session.commit()
    return {"id": body.id, "is_final": body.is_final}


@router.put("/runs/{run_id}/tool-results/{result_id}/consumption")
async def consume_result(
    run_id: str,
    result_id: str,
    body: ConsumptionBody,
    session: AsyncSession = Session,
    _: None = Operator,
) -> dict:
    result = await session.get(ToolInvocationResult, result_id, with_for_update=True)
    exchange = await session.get(Exchange, body.exchange_id)
    if result is None or result.run_id != run_id:
        raise HTTPException(404, "Tool result not found")
    if exchange is None or exchange.run_id != run_id:
        raise HTTPException(422, "Consumption exchange must belong to run")
    if body.consumed_at < result.occurred_at:
        raise HTTPException(422, "Consumption precedes result")
    if result.consumed_at is not None and (result.consumed_at, result.consumed_exchange_id) != (
        body.consumed_at,
        body.exchange_id,
    ):
        raise HTTPException(409, "Result was already consumed at another boundary")
    result.consumed_at, result.consumed_exchange_id = body.consumed_at, body.exchange_id
    await session.commit()
    return {"id": result.id, "consumed_exchange_id": result.consumed_exchange_id}
