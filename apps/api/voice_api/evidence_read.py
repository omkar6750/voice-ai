"""Flow visits and tool-result evidence projected into the shared timeline."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from voice_api.models import FlowNodeVisit, ToolInvocationResult, TraceSpan


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
    }
