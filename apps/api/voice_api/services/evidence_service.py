"""Flow visits and tool-result evidence projected into the shared timeline."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from voice_api.models import (
    ClassifierContextDelivery,
    ClassifierResult,
    FlowNodeVisit,
    InterruptionEvent,
    RunDiagnostic,
    ToolContextDelivery,
    ToolInvocationResult,
    TraceSpan,
)


async def related_evidence(session: AsyncSession, run_id: str) -> dict:
    visits = (
        await session.execute(
            select(FlowNodeVisit, TraceSpan)
            .join(TraceSpan, FlowNodeVisit.span_id == TraceSpan.id)
            .where(FlowNodeVisit.run_id == run_id)
            .order_by(FlowNodeVisit.sequence)
        )
    ).all()
    results = (
        await session.scalars(
            select(ToolInvocationResult)
            .where(ToolInvocationResult.run_id == run_id)
            .order_by(ToolInvocationResult.tool_invocation_id, ToolInvocationResult.sequence)
        )
    ).all()
    deliveries = (
        await session.scalars(
            select(ToolContextDelivery)
            .where(ToolContextDelivery.run_id == run_id)
            .order_by(ToolContextDelivery.delivered_at)
        )
    ).all()
    classifier_results = (
        await session.scalars(
            select(ClassifierResult)
            .where(ClassifierResult.run_id == run_id)
            .order_by(ClassifierResult.occurred_at)
        )
    ).all()
    classifier_deliveries = (
        await session.scalars(
            select(ClassifierContextDelivery)
            .where(ClassifierContextDelivery.run_id == run_id)
            .order_by(ClassifierContextDelivery.delivered_at)
        )
    ).all()
    interruptions = (
        await session.scalars(
            select(InterruptionEvent)
            .where(InterruptionEvent.run_id == run_id)
            .order_by(InterruptionEvent.occurred_at)
        )
    ).all()
    diagnostics = (
        await session.scalars(
            select(RunDiagnostic)
            .where(RunDiagnostic.run_id == run_id)
            .order_by(RunDiagnostic.occurred_at)
        )
    ).all()
    return {
        "flow_visits": [
            {
                "id": v.id,
                "sequence": v.sequence,
                "node_key": v.node_key,
                "span_id": s.id,
                "entered_at": s.started_at,
                "exited_at": s.ended_at,
                "triggered_by_tool_id": v.triggered_by_tool_id,
            }
            for v, s in visits
        ],
        "tool_results": [
            {
                "id": r.id,
                "tool_invocation_id": r.tool_invocation_id,
                "sequence": r.sequence,
                "payload": r.payload,
                "is_final": r.is_final,
                "occurred_at": r.occurred_at,
                "consumed_at": r.consumed_at,
                "consumed_exchange_id": r.consumed_exchange_id,
            }
            for r in results
        ],
        "tool_context_deliveries": [
            {
                "id": d.id,
                "run_id": d.run_id,
                "tool_invocation_id": d.tool_invocation_id,
                "result_id": d.result_id,
                "function_call_id": d.function_call_id,
                "is_final": d.is_final,
                "status": d.status,
                "context_message_index": d.context_message_index,
                "delivered_at": d.delivered_at,
                "consumed_at": d.consumed_at,
                "consumed_exchange_id": d.consumed_exchange_id,
                "consuming_span_id": d.consuming_span_id,
            }
            for d in deliveries
        ],
        "classifier_results": [
            {
                "id": result.id,
                "run_id": result.run_id,
                "operation_id": result.operation_id,
                "phase": result.phase,
                "node_key": result.node_key,
                "classifier_type": result.classifier_type,
                "status": result.status,
                "result": result.result,
                "error": result.error,
                "transcript_sha256": result.transcript_sha256,
                "occurred_at": result.occurred_at,
            }
            for result in classifier_results
        ],
        "classifier_context_deliveries": [
            {
                "id": delivery.id,
                "run_id": delivery.run_id,
                "classifier_result_id": delivery.classifier_result_id,
                "operation_id": delivery.operation_id,
                "phase": delivery.phase,
                "node_key": delivery.node_key,
                "status": delivery.status,
                "context_message_index": delivery.context_message_index,
                "delivered_at": delivery.delivered_at,
                "consumed_at": delivery.consumed_at,
                "consumed_exchange_id": delivery.consumed_exchange_id,
                "consuming_operation_id": delivery.consuming_operation_id,
            }
            for delivery in classifier_deliveries
        ],
        "interruptions": [
            {
                "id": interruption.id,
                "run_id": interruption.run_id,
                "exchange_id": interruption.exchange_id,
                "source": interruption.source,
                "reason": interruption.reason,
                "frame_type": interruption.frame_type,
                "interrupted_operation_ids": interruption.interrupted_operation_ids,
                "interrupted_tool_invocation_ids": interruption.interrupted_tool_invocation_ids,
                "occurred_at": interruption.occurred_at,
            }
            for interruption in interruptions
        ],
        "diagnostics": [
            {
                "diagnostic_id": diagnostic.id,
                "run_id": diagnostic.run_id,
                "severity": diagnostic.severity,
                "category": diagnostic.category,
                "source": diagnostic.source,
                "code": diagnostic.code,
                "message": diagnostic.message,
                "detail": diagnostic.detail,
                "retryable": diagnostic.retryable,
                "uncertain": diagnostic.uncertain,
                "provider_request_id": diagnostic.provider_request_id,
                "http_status": diagnostic.http_status,
                "retry_after_seconds": diagnostic.retry_after_seconds,
                "metadata": diagnostic.metadata_json,
                "occurred_at": diagnostic.occurred_at,
                "created_at": diagnostic.created_at,
            }
            for diagnostic in diagnostics
        ],
    }
