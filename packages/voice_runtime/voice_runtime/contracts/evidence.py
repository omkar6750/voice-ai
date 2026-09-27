"""Versioned finalized evidence protocol shared by spool client and control plane."""

from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, JsonValue

from .base import ConfigModel

Id = Annotated[str, Field(min_length=1, max_length=36)]
TimestampNs = Annotated[int, Field(gt=0, le=253402300799000000000)]


class Record(ConfigModel):
    id: Id
    run_id: Id
    timestamp_ns: TimestampNs


class ExchangeRecord(Record):
    kind: Literal["exchange"]
    exchange_id: Id
    sequence: int = Field(gt=0)
    origin: Literal["greeting", "caller", "agent"]


class ExchangeEnded(Record):
    kind: Literal["exchange_ended"]
    exchange_id: Id
    status: Literal["completed", "interrupted", "failed"]


class MessageRecord(Record):
    kind: Literal["message"]
    exchange_id: Id
    sequence: int = Field(gt=0)
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=100000)
    source_timestamp: AwareDatetime
    finalized: Literal[True] = True
    interrupted: bool = False


class OperationStarted(Record):
    kind: Literal["operation_started"]
    operation_id: Id
    exchange_id: Id | None = None
    name: str = Field(min_length=1, max_length=120)
    category: str = Field(min_length=1, max_length=40)
    parent_id: Id | None = None
    started_ns: TimestampNs
    provider: str | None = Field(default=None, max_length=60)
    model: str | None = Field(default=None, max_length=160)
    otel_trace_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")
    otel_span_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{16}$")
    input_payload: dict | list | None = None
    attributes: dict = Field(default_factory=dict)


class OperationEnded(OperationStarted):
    kind: Literal["span"]
    ended_ns: TimestampNs
    duration_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    status: Literal["completed", "failed", "cancelled", "interrupted"]
    output_state: Literal[
        "recorded", "not_applicable", "not_recorded", "empty", "interrupted", "failed"
    ] = "not_recorded"
    interruption_id: Id | None = None
    output_payload: dict | list | None = None
    ttfb_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    ttfa_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    ttfat_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)
    audio_seconds: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class FlowVisitStarted(Record):
    kind: Literal["flow_visit_started"]
    visit_id: Id
    span_id: Id
    sequence: int = Field(gt=0)
    node_key: str = Field(min_length=1, max_length=120)
    started_ns: TimestampNs
    triggered_by_tool_id: Id | None = None


class FlowVisitEnded(Record):
    kind: Literal["flow_visit_ended"]
    visit_id: Id
    ended_ns: TimestampNs
    duration_ms: float = Field(ge=0, allow_inf_nan=False)
    status: Literal["completed", "interrupted", "failed"]


class ToolStarted(Record):
    kind: Literal["tool_started"]
    invocation_id: Id
    exchange_id: Id | None = None
    binding_key: str = Field(min_length=1, max_length=80)
    tool_version_id: Id | None = None
    function_call_id: str | None = Field(default=None, max_length=255)
    llm_operation_id: Id | None = None
    arguments: dict = Field(default_factory=dict)
    started_ns: TimestampNs


class ToolEnded(Record):
    kind: Literal["tool_ended"]
    invocation_id: Id
    ended_ns: TimestampNs
    status: Literal["completed", "failed", "cancelled", "uncertain"]
    result: JsonValue = None
    connection_id: Id | None = None
    provider_message_id: str | None = Field(default=None, max_length=255)
    interruption_id: Id | None = None


class ToolResultRecorded(Record):
    kind: Literal["tool_result"]
    invocation_id: Id
    sequence: int = Field(gt=0)
    payload: JsonValue
    is_final: bool


class ToolResultContextUpdated(Record):
    kind: Literal["tool_result_context_updated"]
    delivery_id: Id
    invocation_id: Id
    result_id: Id
    function_call_id: str | None = Field(default=None, max_length=255)
    is_final: bool
    context_message_index: int | None = Field(default=None, ge=0)


class ToolResultConsumed(Record):
    kind: Literal["tool_result_consumed"]
    result_id: Id
    exchange_id: Id
    invocation_id: Id | None = None
    function_call_id: str | None = Field(default=None, max_length=255)
    consuming_operation_id: Id | None = None


class ClassifierResultRecorded(Record):
    kind: Literal["classifier_result"]
    result_id: Id
    operation_id: Id
    phase: Literal["entry", "exit"]
    node_key: str = Field(min_length=1, max_length=120)
    classifier_type: Literal["llm", "jev"]
    status: Literal["completed", "failed"]
    result: JsonValue = None
    error: str | None = Field(default=None, max_length=500)
    transcript_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ClassifierContextUpdated(Record):
    kind: Literal["classifier_context_updated"]
    delivery_id: Id
    result_id: Id
    operation_id: Id
    phase: Literal["entry", "exit"]
    node_key: str = Field(min_length=1, max_length=120)
    context_message_index: int = Field(ge=0)


class ClassifierResultConsumed(Record):
    kind: Literal["classifier_result_consumed"]
    result_id: Id
    exchange_id: Id
    consuming_operation_id: Id


class InterruptionRecord(Record):
    kind: Literal["interruption"]
    interruption_id: Id
    exchange_id: Id | None = None
    source: Literal["caller", "system", "transport"]
    reason: str = Field(min_length=1, max_length=255)
    frame_type: str = Field(min_length=1, max_length=120)
    interrupted_operation_ids: list[Id] = Field(default_factory=list)
    interrupted_tool_invocation_ids: list[Id] = Field(default_factory=list)


class DiagnosticRecord(Record):
    kind: Literal["diagnostic"]
    diagnostic_id: Id
    severity: Literal["info", "warning", "error"]
    category: str = Field(min_length=1, max_length=80)
    source: Literal["provider", "modem", "transport", "call", "evidence", "runtime"]
    code: str | None = Field(default=None, max_length=120)
    message: str = Field(min_length=1, max_length=500)
    detail: str | None = Field(default=None, max_length=2000)
    retryable: bool = False
    uncertain: bool = False
    provider_request_id: str | None = Field(default=None, max_length=255)
    http_status: int | None = Field(default=None, ge=100, le=599)
    retry_after_seconds: float | None = Field(default=None, ge=0, le=86400)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


EvidenceRecord = Annotated[
    ExchangeRecord
    | ExchangeEnded
    | MessageRecord
    | OperationStarted
    | OperationEnded
    | FlowVisitStarted
    | FlowVisitEnded
    | ToolStarted
    | ToolEnded
    | ToolResultRecorded
    | ToolResultContextUpdated
    | ToolResultConsumed
    | ClassifierResultRecorded
    | ClassifierContextUpdated
    | ClassifierResultConsumed
    | InterruptionRecord
    | DiagnosticRecord,
    Field(discriminator="kind"),
]


class EvidenceBatch(ConfigModel):
    schema_version: Literal[1] = 1
    records: list[EvidenceRecord] = Field(min_length=1, max_length=200)
