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


class ToolResultRecorded(Record):
    kind: Literal["tool_result"]
    invocation_id: Id
    sequence: int = Field(gt=0)
    payload: JsonValue
    is_final: bool


class ToolResultConsumed(Record):
    kind: Literal["tool_result_consumed"]
    result_id: Id
    exchange_id: Id


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
    | ToolResultConsumed,
    Field(discriminator="kind"),
]


class EvidenceBatch(ConfigModel):
    schema_version: Literal[1] = 1
    records: list[EvidenceRecord] = Field(min_length=1, max_length=200)
