"""Typed run timeline response contracts."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, JsonValue

from voice_api.schemas.diagnostics import DiagnosticResponse


class TimelineRun(BaseModel):
    id: str
    status: str
    agent_id: str
    agent_version_id: str
    evidence_complete: bool | None = None


class TimelineCall(BaseModel):
    id: str
    status: str
    provider: str
    provider_call_id: str | None
    answered_at: datetime | None
    ended_at: datetime | None


class TimelineExchange(BaseModel):
    id: str
    sequence: int
    origin: str
    status: str
    created_at: datetime
    ended_at: datetime | None


class TimelineMessage(BaseModel):
    id: str
    exchange_id: str
    role: str
    sequence: int
    content: str
    interrupted: bool
    created_at: datetime
    source_at: datetime | None
    playback_started_at: datetime | None
    playback_ended_at: datetime | None


class TimelineSpan(BaseModel):
    id: str
    exchange_id: str | None
    parent_id: str | None
    name: str
    category: str
    status: str
    output_state: str
    interruption_id: str | None
    started_at: datetime
    ended_at: datetime | None
    attributes: dict[str, Any]
    provider: str | None
    model: str | None
    otel_trace_id: str | None
    otel_span_id: str | None
    duration_ms: float | None
    ttfb_ms: float | None
    ttfa_ms: float | None
    ttfat_ms: float | None
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    cache_read_input_tokens: int | None
    cache_creation_input_tokens: int | None
    reasoning_tokens: int | None
    audio_seconds: float | None
    input: JsonValue | None
    output: JsonValue | None


class TimelineToolReceipt(BaseModel):
    """Sanitized WhatsApp delivery status received for an outbound message."""

    status: str
    timestamp: str | None = None
    recipient_id: str | None = None
    errors: list[JsonValue] = Field(default_factory=list)


class TimelineTool(BaseModel):
    id: str
    exchange_id: str | None
    llm_operation_id: str | None
    function_call_id: str | None
    binding_key: str
    status: str
    interruption_id: str | None
    arguments: dict[str, Any]
    result: JsonValue | None
    started_at: datetime
    ended_at: datetime | None
    provider_message_id: str | None
    receipts: list[TimelineToolReceipt]


class TimelineToolResult(BaseModel):
    id: str
    tool_invocation_id: str
    sequence: int
    payload: JsonValue
    is_final: bool
    occurred_at: datetime
    consumed_at: datetime | None
    consumed_exchange_id: str | None


class ToolContextDeliveryResponse(BaseModel):
    id: str
    run_id: str
    tool_invocation_id: str
    result_id: str
    function_call_id: str | None
    is_final: bool
    status: str
    context_message_index: int | None
    delivered_at: datetime
    consumed_at: datetime | None
    consumed_exchange_id: str | None
    consuming_span_id: str | None


class ClassifierResultResponse(BaseModel):
    id: str
    run_id: str
    operation_id: str
    phase: str
    node_key: str
    classifier_type: str
    status: str
    result: JsonValue | None
    error: str | None
    transcript_sha256: str
    occurred_at: datetime


class ClassifierContextDeliveryResponse(BaseModel):
    id: str
    run_id: str
    classifier_result_id: str
    operation_id: str
    phase: str
    node_key: str
    status: str
    context_message_index: int
    delivered_at: datetime
    consumed_at: datetime | None
    consumed_exchange_id: str | None
    consuming_operation_id: str | None


class RunContextEventResponse(BaseModel):
    id: str
    run_id: str
    tool_invocation_id: str | None
    source: Literal["tool_result", "whatsapp_receipt"]
    source_reference: str | None
    connection_id: str | None
    provider_message_id: str | None
    payload: JsonValue
    status: Literal["pending", "delivered", "consumed", "ended_before_delivery"]
    occurred_at: datetime
    delivered_at: datetime | None
    context_message_index: int | None
    consumed_at: datetime | None
    consumed_exchange_id: str | None
    consuming_span_id: str | None


class InterruptionResponse(BaseModel):
    id: str
    run_id: str
    exchange_id: str | None
    source: str
    reason: str
    frame_type: str
    interrupted_operation_ids: list[str]
    interrupted_tool_invocation_ids: list[str]
    occurred_at: datetime


class TimelineFlowVisit(BaseModel):
    id: str
    sequence: int
    node_key: str
    span_id: str
    entered_at: datetime
    exited_at: datetime | None
    triggered_by_tool_id: str | None


class TimelineResponse(BaseModel):
    run: TimelineRun
    call: TimelineCall | None
    exchanges: list[TimelineExchange]
    messages: list[TimelineMessage]
    spans: list[TimelineSpan]
    tools: list[TimelineTool]
    tool_results: list[TimelineToolResult]
    tool_context_deliveries: list[ToolContextDeliveryResponse]
    classifier_results: list[ClassifierResultResponse]
    classifier_context_deliveries: list[ClassifierContextDeliveryResponse]
    context_events: list[RunContextEventResponse]
    interruptions: list[InterruptionResponse]
    diagnostics: list[DiagnosticResponse]
    flow_visits: list[TimelineFlowVisit]
