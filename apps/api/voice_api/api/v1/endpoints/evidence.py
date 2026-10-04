"""Durable flow visits, tool results, and streaming evidence ingestion."""

from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from voice_api.api.deps import get_session, require_runtime_service
from voice_api.core.security import safe_evidence
from voice_api.db.tenant_scope import bind_run_organization
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
from voice_runtime.contracts.evidence import (
    ClassifierContextUpdated,
    ClassifierResultConsumed,
    ClassifierResultRecorded,
    DiagnosticRecord,
    EvidenceBatch,
    ExchangeEnded,
    ExchangeRecord,
    FlowVisitEnded,
    FlowVisitStarted,
    InterruptionRecord,
    MessageRecord,
    OperationEnded,
    OperationStarted,
    ToolEnded,
    ToolResultConsumed,
    ToolResultContextUpdated,
    ToolResultRecorded,
    ToolStarted,
)

router = APIRouter(tags=["evidence"])
Session = Depends(get_session)
Operator = Depends(require_runtime_service)
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
    consuming_operation_id: Id | None = None


def at_ns(value: int) -> datetime:
    seconds, nanoseconds = divmod(value, 1000000000)
    return datetime(1970, 1, 1, tzinfo=UTC) + timedelta(
        seconds=seconds, microseconds=nanoseconds // 1000
    )


def verify_same(existing, fields: dict) -> None:
    if any(getattr(existing, key) != value for key, value in fields.items()):
        raise HTTPException(409, "Evidence identity conflicts with existing record")


def verify_delivery_replay(existing, fields: dict) -> None:
    # A replayed delivery can arrive after its later consumption was persisted.
    if existing.status not in {"delivered", "consumed"}:
        raise HTTPException(409, "Evidence delivery has an incompatible state")
    verify_same(existing, {key: value for key, value in fields.items() if key != "status"})


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
    if isinstance(record, ExchangeEnded):
        row = await session.get(Exchange, record.exchange_id)
        if row is None or row.run_id != run_id:
            raise HTTPException(422, "Exchange must belong to run")
        ended_at = at_ns(record.timestamp_ns)
        if ended_at < row.created_at:
            raise HTTPException(422, "Exchange end precedes start")
        if row.ended_at is not None:
            verify_same(row, {"ended_at": ended_at, "status": record.status})
        else:
            row.ended_at, row.status = ended_at, record.status
        await session.flush()
        return
    if isinstance(record, FlowVisitStarted):
        run = await session.get(Run, run_id)
        nodes = run.resolved_config.get("flow", {}).get("nodes", [])
        if record.node_key not in {node["id"] for node in nodes}:
            raise HTTPException(422, "Node is absent from resolved flow")
        if record.triggered_by_tool_id:
            trigger = await session.get(ToolInvocation, record.triggered_by_tool_id)
            if trigger is None or trigger.run_id != run_id:
                raise HTTPException(422, "Flow trigger must belong to run")
        started_at = at_ns(record.started_ns)
        visit = await session.get(FlowNodeVisit, record.visit_id)
        if visit is not None:
            verify_same(
                visit,
                {
                    "run_id": run_id,
                    "span_id": record.span_id,
                    "sequence": record.sequence,
                    "node_key": record.node_key,
                    "triggered_by_tool_id": record.triggered_by_tool_id,
                },
            )
            verify_same(await session.get(TraceSpan, visit.span_id), {"started_at": started_at})
        else:
            session.add(
                TraceSpan(
                    id=record.span_id,
                    run_id=run_id,
                    name=record.node_key,
                    category="flow_node",
                    status="running",
                    started_at=started_at,
                )
            )
            await session.flush()
            session.add(
                FlowNodeVisit(
                    id=record.visit_id,
                    run_id=run_id,
                    span_id=record.span_id,
                    sequence=record.sequence,
                    node_key=record.node_key,
                    triggered_by_tool_id=record.triggered_by_tool_id,
                )
            )
        await session.flush()
        return
    if isinstance(record, FlowVisitEnded):
        visit = await session.get(FlowNodeVisit, record.visit_id)
        if visit is None or visit.run_id != run_id:
            raise HTTPException(422, "Flow visit must belong to run")
        span = await session.get(TraceSpan, visit.span_id)
        ended_at = at_ns(record.ended_ns)
        if ended_at < span.started_at:
            raise HTTPException(422, "Flow exit precedes entry")
        fields = {
            "ended_at": ended_at,
            "duration_ms": record.duration_ms,
            "status": record.status,
        }
        if span.ended_at is not None:
            verify_same(span, fields)
        else:
            for key, value in fields.items():
                setattr(span, key, value)
        await session.flush()
        return
    if isinstance(record, ClassifierResultRecorded):
        operation = await session.get(TraceSpan, record.operation_id)
        if operation is None:
            session.add(
                TraceSpan(
                    id=record.operation_id,
                    run_id=run_id,
                    name="classifier",
                    category="classifier",
                    status=record.status,
                    started_at=at_ns(record.timestamp_ns),
                    ended_at=at_ns(record.timestamp_ns),
                )
            )
        else:
            if operation.run_id != run_id:
                raise HTTPException(422, "Classifier operation belongs to different run")
            operation.category = "classifier"
            operation.status = record.status
            if operation.ended_at is None:
                operation.ended_at = at_ns(record.timestamp_ns)
        fields = {
            "run_id": run_id,
            "operation_id": record.operation_id,
            "phase": record.phase,
            "node_key": record.node_key,
            "classifier_type": record.classifier_type,
            "status": record.status,
            "result": record.result,
            "error": record.error,
            "transcript_sha256": record.transcript_sha256,
            "occurred_at": at_ns(record.timestamp_ns),
        }
        row = await session.get(ClassifierResult, record.result_id)
        if row:
            verify_same(row, fields)
        else:
            session.add(ClassifierResult(id=record.result_id, **fields))
        await session.flush()
        return
    if isinstance(record, ClassifierContextUpdated):
        result = await session.get(ClassifierResult, record.result_id)
        operation = await session.get(TraceSpan, record.operation_id)
        if (
            result is None
            or result.run_id != run_id
            or result.operation_id != record.operation_id
            or operation is None
            or operation.run_id != run_id
        ):
            raise HTTPException(422, "Classifier context delivery must reference its result")
        fields = {
            "run_id": run_id,
            "classifier_result_id": record.result_id,
            "operation_id": record.operation_id,
            "phase": record.phase,
            "node_key": record.node_key,
            "status": "delivered",
            "context_message_index": record.context_message_index,
            "delivered_at": at_ns(record.timestamp_ns),
        }
        delivery = await session.get(ClassifierContextDelivery, record.delivery_id)
        if delivery:
            verify_delivery_replay(delivery, fields)
        else:
            existing = await session.scalar(
                select(ClassifierContextDelivery).where(
                    ClassifierContextDelivery.classifier_result_id == record.result_id
                )
            )
            if existing:
                verify_delivery_replay(existing, fields)
            else:
                session.add(ClassifierContextDelivery(id=record.delivery_id, **fields))
        await session.flush()
        return
    if isinstance(record, ClassifierResultConsumed):
        result = await session.get(ClassifierResult, record.result_id)
        exchange = await session.get(Exchange, record.exchange_id)
        operation = await session.get(TraceSpan, record.consuming_operation_id)
        if (
            result is None
            or result.run_id != run_id
            or exchange is None
            or exchange.run_id != run_id
            or operation is None
            or operation.run_id != run_id
            or operation.category != "llm"
        ):
            raise HTTPException(422, "Classifier consumption must belong to this run")
        delivery = await session.scalar(
            select(ClassifierContextDelivery).where(
                ClassifierContextDelivery.classifier_result_id == record.result_id
            )
        )
        if delivery is None:
            raise HTTPException(422, "Classifier consumption requires context delivery")
        fields = {
            "status": "consumed",
            "consumed_at": at_ns(record.timestamp_ns),
            "consumed_exchange_id": record.exchange_id,
            "consuming_operation_id": record.consuming_operation_id,
        }
        if delivery.status == "consumed":
            verify_same(delivery, fields)
        else:
            for key, value in fields.items():
                setattr(delivery, key, value)
        await session.flush()
        return
    if isinstance(record, InterruptionRecord):
        if record.exchange_id is not None:
            exchange = await session.get(Exchange, record.exchange_id)
            if exchange is None or exchange.run_id != run_id:
                raise HTTPException(422, "Interruption exchange must belong to run")
        for operation_id in record.interrupted_operation_ids:
            operation = await session.get(TraceSpan, operation_id)
            if operation is None or operation.run_id != run_id:
                raise HTTPException(422, "Interruption operation must belong to run")
        for invocation_id in record.interrupted_tool_invocation_ids:
            invocation = await session.get(ToolInvocation, invocation_id)
            if invocation is None or invocation.run_id != run_id:
                raise HTTPException(422, "Interruption tool must belong to run")
        fields = {
            "run_id": run_id,
            "exchange_id": record.exchange_id,
            "source": record.source,
            "reason": record.reason,
            "frame_type": record.frame_type,
            "interrupted_operation_ids": record.interrupted_operation_ids,
            "interrupted_tool_invocation_ids": record.interrupted_tool_invocation_ids,
            "occurred_at": at_ns(record.timestamp_ns),
        }
        row = await session.get(InterruptionEvent, record.interruption_id)
        if row:
            verify_same(row, fields)
        else:
            session.add(InterruptionEvent(id=record.interruption_id, **fields))
        await session.flush()
        return
    if isinstance(record, DiagnosticRecord):
        fields = {
            "run_id": run_id,
            "severity": record.severity,
            "category": record.category,
            "source": record.source,
            "code": record.code,
            "message": record.message,
            "detail": record.detail,
            "retryable": record.retryable,
            "uncertain": record.uncertain,
            "provider_request_id": record.provider_request_id,
            "http_status": record.http_status,
            "retry_after_seconds": record.retry_after_seconds,
            "metadata_json": record.metadata,
            "occurred_at": at_ns(record.timestamp_ns),
        }
        row = await session.get(RunDiagnostic, record.diagnostic_id)
        if row:
            verify_same(row, fields)
        else:
            session.add(RunDiagnostic(id=record.diagnostic_id, **fields))
        await session.flush()
        return
    if isinstance(record, ToolStarted):
        if record.exchange_id is not None:
            exchange = await session.get(Exchange, record.exchange_id)
            if exchange is None or exchange.run_id != run_id:
                raise HTTPException(422, "Tool exchange must belong to run")
        run = await session.get(Run, run_id)
        binding = run.resolved_config.get("_resolved", {}).get("tools", {}).get(record.binding_key)
        generated = False
        if binding is None and record.tool_version_id is None:
            # Generated fact/edge tools belong to the frozen flow, not the registry.
            at = at_ns(record.started_ns)
            node_key = await session.scalar(
                select(FlowNodeVisit.node_key)
                .join(TraceSpan, TraceSpan.id == FlowNodeVisit.span_id)
                .where(FlowNodeVisit.run_id == run_id, TraceSpan.started_at <= at)
                .order_by(TraceSpan.started_at.desc())
                .limit(1)
            )
            node = next(
                (
                    n
                    for n in run.resolved_config.get("flow", {}).get("nodes", [])
                    if n["id"] == node_key
                ),
                {},
            )
            generated = (
                any(
                    record.binding_key == f"record_{slot['key']}"
                    and (not slot.get("nodes") or node_key in slot["nodes"])
                    for slot in run.resolved_config.get("fact_slots", [])
                )
                if node
                else False
            )
            generated = (
                generated
                or record.binding_key
                in {f"go_to_{target}" for target in node.get("transitions", [])}
                or any(
                    fn.get("transition_only") and fn["name"] == record.binding_key
                    for fn in node.get("functions", [])
                )
            )
        if not generated and (
            binding is None or binding.get("version_id") != record.tool_version_id
        ):
            raise HTTPException(422, "Tool binding is absent from run snapshot")
        if record.llm_operation_id:
            operation = await session.get(TraceSpan, record.llm_operation_id)
            if operation is None or operation.run_id != run_id:
                raise HTTPException(422, "Tool inference must belong to run")
        fields = {
            "run_id": run_id,
            "exchange_id": record.exchange_id,
            "tool_version_id": record.tool_version_id,
            "binding_key": record.binding_key,
            "function_call_id": record.function_call_id,
            "llm_operation_id": record.llm_operation_id,
            "arguments": record.arguments,
            "started_at": at_ns(record.started_ns),
        }
        row = await session.get(ToolInvocation, record.invocation_id)
        if row:
            verify_same(row, fields)
        else:
            session.add(
                ToolInvocation(
                    id=record.invocation_id,
                    idempotency_key=record.invocation_id,
                    status="running",
                    **fields,
                )
            )
        await session.flush()
        return
    if isinstance(record, ToolEnded):
        row = await session.get(ToolInvocation, record.invocation_id)
        if row is None or row.run_id != run_id:
            raise HTTPException(422, "Tool invocation must belong to run")
        ended_at = at_ns(record.ended_ns)
        if ended_at < row.started_at:
            raise HTTPException(422, "Tool end precedes start")
        fields = {
            "ended_at": ended_at,
            "status": record.status,
            "result": record.result,
            "connection_id": record.connection_id,
            "provider_message_id": record.provider_message_id,
            "interruption_id": record.interruption_id,
        }
        if row.ended_at is not None:
            verify_same(row, fields)
        else:
            for key, value in fields.items():
                setattr(row, key, value)
        await session.flush()
        return
    if isinstance(record, ToolResultRecorded):
        tool = await session.get(ToolInvocation, record.invocation_id)
        if tool is None or tool.run_id != run_id:
            raise HTTPException(422, "Tool result requires an invocation")
        fields = {
            "run_id": run_id,
            "tool_invocation_id": record.invocation_id,
            "sequence": record.sequence,
            "payload": record.payload,
            "is_final": record.is_final,
            "occurred_at": at_ns(record.timestamp_ns),
        }
        row = await session.get(ToolInvocationResult, record.id)
        if row:
            verify_same(row, fields)
        else:
            session.add(ToolInvocationResult(id=record.id, **fields))
        await session.flush()
        return
    if isinstance(record, ToolResultContextUpdated):
        result = await session.get(ToolInvocationResult, record.result_id)
        invocation = await session.get(ToolInvocation, record.invocation_id)
        if (
            result is None
            or result.run_id != run_id
            or invocation is None
            or invocation.run_id != run_id
            or result.tool_invocation_id != record.invocation_id
        ):
            raise HTTPException(422, "Context delivery must reference its tool result")
        fields = {
            "run_id": run_id,
            "tool_invocation_id": record.invocation_id,
            "result_id": record.result_id,
            "function_call_id": record.function_call_id,
            "is_final": record.is_final,
            "status": "delivered",
            "context_message_index": record.context_message_index,
            "delivered_at": at_ns(record.timestamp_ns),
        }
        delivery = await session.get(ToolContextDelivery, record.delivery_id)
        if delivery is None:
            existing = await session.scalar(
                select(ToolContextDelivery).where(ToolContextDelivery.result_id == record.result_id)
            )
            if existing is not None:
                verify_delivery_replay(existing, fields)
            else:
                session.add(ToolContextDelivery(id=record.delivery_id, **fields))
        else:
            verify_delivery_replay(delivery, fields)
        await session.flush()
        return
    if isinstance(record, ToolResultConsumed):
        result = await session.get(ToolInvocationResult, record.result_id)
        exchange = await session.get(Exchange, record.exchange_id)
        if (
            result is None
            or result.run_id != run_id
            or exchange is None
            or exchange.run_id != run_id
        ):
            raise HTTPException(422, "Consumption must belong to run")
        if record.invocation_id is not None and result.tool_invocation_id != record.invocation_id:
            raise HTTPException(422, "Consumption invocation does not match the result")
        consumed_at = at_ns(record.timestamp_ns)
        if consumed_at < result.occurred_at:
            raise HTTPException(422, "Consumption precedes result")
        fields = {"consumed_at": consumed_at, "consumed_exchange_id": record.exchange_id}
        if result.consumed_at is not None:
            verify_same(result, fields)
        else:
            for key, value in fields.items():
                setattr(result, key, value)
        if record.consuming_operation_id is not None:
            operation = await session.get(TraceSpan, record.consuming_operation_id)
            if operation is None or operation.run_id != run_id:
                raise HTTPException(422, "Consuming operation must belong to run")
            delivery = await session.scalar(
                select(ToolContextDelivery).where(ToolContextDelivery.result_id == record.result_id)
            )
            if delivery is not None:
                delivery_fields = {
                    "status": "consumed",
                    "consumed_at": consumed_at,
                    "consumed_exchange_id": record.exchange_id,
                    "consuming_span_id": record.consuming_operation_id,
                }
                if delivery.status == "consumed":
                    verify_same(delivery, delivery_fields)
                else:
                    for key, value in delivery_fields.items():
                        setattr(delivery, key, value)
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
    elif isinstance(record, (OperationStarted, OperationEnded)):
        fields = dict(
            run_id=run_id,
            exchange_id=record.exchange_id,
            name=record.name,
            category=record.category,
            parent_id=record.parent_id,
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
                output_state=record.output_state,
                interruption_id=record.interruption_id,
                attributes=record.attributes,
                output_payload=record.output_payload,
                ttfb_ms=record.ttfb_ms,
                ttfa_ms=record.ttfa_ms,
                ttfat_ms=record.ttfat_ms,
                prompt_tokens=record.prompt_tokens,
                completion_tokens=record.completion_tokens,
                total_tokens=record.total_tokens,
                cache_read_input_tokens=record.cache_read_input_tokens,
                cache_creation_input_tokens=record.cache_creation_input_tokens,
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
    else:
        raise TypeError(f"Evidence mapping is missing for {type(record).__name__}")
    await session.flush()


@router.post("/runs/{run_id}/evidence")
async def ingest(
    run_id: str, body: EvidenceBatch, session: AsyncSession = Session, _: None = Operator
) -> dict:
    await bind_run_organization(session, run_id)
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
    await bind_run_organization(session, run_id)
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
    await bind_run_organization(session, run_id)
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
    await bind_run_organization(session, run_id)
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
    if body.consuming_operation_id is not None:
        operation = await session.get(TraceSpan, body.consuming_operation_id)
        if operation is None or operation.run_id != run_id:
            raise HTTPException(422, "Consuming operation must belong to run")
        delivery = await session.scalar(
            select(ToolContextDelivery).where(ToolContextDelivery.result_id == result_id)
        )
        if delivery is not None:
            delivery.status = "consumed"
            delivery.consumed_at = body.consumed_at
            delivery.consumed_exchange_id = body.exchange_id
            delivery.consuming_span_id = body.consuming_operation_id
    await session.commit()
    return {"id": result.id, "consumed_exchange_id": result.consumed_exchange_id}
