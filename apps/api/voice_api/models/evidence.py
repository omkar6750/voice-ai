from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .common import JSONB, Base, Created, Identity, now


class Run(Identity, Created, Base):
    __tablename__ = "runs"
    channel: Mapped[str] = mapped_column(String(20), default="phone", server_default="phone")
    contact_id: Mapped[str | None] = mapped_column(ForeignKey("contacts.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    agent_version_id: Mapped[str] = mapped_column(ForeignKey("agent_versions.id"), index=True)
    endpoint_id: Mapped[str | None] = mapped_column(ForeignKey("runtime_endpoints.id"), index=True)
    resolved_config: Mapped[dict] = mapped_column(JSONB)
    contact_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)


class Call(Identity, Created, Base):
    __tablename__ = "calls"
    __table_args__ = (UniqueConstraint("run_id"),)
    provider: Mapped[str] = mapped_column(String(40), default="sim7600", server_default="sim7600")
    provider_call_id: Mapped[str | None] = mapped_column(String(255))
    correlation_id: Mapped[str | None] = mapped_column(String(36), unique=True)
    provider_metadata: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    run_id: Mapped[str | None] = mapped_column(ForeignKey("runs.id"), index=True)
    contact_id: Mapped[str] = mapped_column(ForeignKey("contacts.id"), index=True)
    agent_version_id: Mapped[str] = mapped_column(ForeignKey("agent_versions.id"), index=True)
    target_snapshot: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    modem_start: Mapped[dict] = mapped_column(JSONB, default=dict)
    modem_end: Mapped[dict] = mapped_column(JSONB, default=dict)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recording_path: Mapped[str | None] = mapped_column(String(500))


class Exchange(Identity, Created, Base):
    __tablename__ = "exchanges"
    __table_args__ = (
        UniqueConstraint("call_id", "sequence"),
        UniqueConstraint("run_id", "sequence"),
        UniqueConstraint("id", "run_id"),
    )
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    # Legacy linkage is preserved; new evidence uses run_id (ADR-0007).
    call_id: Mapped[str | None] = mapped_column(
        ForeignKey("calls.id", ondelete="CASCADE"), index=True
    )
    sequence: Mapped[int]
    origin: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(30), default="active")
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ConversationMessage(Identity, Created, Base):
    __tablename__ = "conversation_messages"
    __table_args__ = (
        UniqueConstraint("exchange_id", "sequence"),
        ForeignKeyConstraint(
            ["exchange_id", "run_id"],
            ["exchanges.id", "exchanges.run_id"],
            ondelete="CASCADE",
            name="fk_message_exchange_run",
        ),
    )
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    exchange_id: Mapped[str] = mapped_column(
        ForeignKey("exchanges.id", ondelete="CASCADE"), index=True
    )
    sequence: Mapped[int]
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    source_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    interrupted: Mapped[bool] = mapped_column(default=False)
    playback_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    playback_ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TraceSpan(Identity, Base):
    __tablename__ = "trace_spans"
    __table_args__ = (UniqueConstraint("id", "run_id"),)
    provider: Mapped[str | None] = mapped_column(String(60))
    model: Mapped[str | None] = mapped_column(String(160))
    otel_trace_id: Mapped[str | None] = mapped_column(String(32))
    otel_span_id: Mapped[str | None] = mapped_column(String(16))
    input_payload: Mapped[dict | list | None] = mapped_column(JSONB(none_as_null=True))
    output_payload: Mapped[dict | list | None] = mapped_column(JSONB(none_as_null=True))
    ttfb_ms: Mapped[float | None]
    ttfa_ms: Mapped[float | None]
    ttfat_ms: Mapped[float | None]
    prompt_tokens: Mapped[int | None]
    completion_tokens: Mapped[int | None]
    reasoning_tokens: Mapped[int | None]
    audio_seconds: Mapped[float | None]
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    exchange_id: Mapped[str | None] = mapped_column(
        ForeignKey("exchanges.id", ondelete="SET NULL"), index=True
    )
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("trace_spans.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(30), default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[float | None]
    attributes: Mapped[dict] = mapped_column(JSONB, default=dict)


class ToolInvocation(Identity, Base):
    __tablename__ = "tool_invocations"
    __table_args__ = (
        UniqueConstraint("run_id", "idempotency_key"),
        UniqueConstraint("id", "run_id"),
        ForeignKeyConstraint(
            ["llm_operation_id", "run_id"],
            ["trace_spans.id", "trace_spans.run_id"],
            name="fk_tool_llm_run",
        ),
    )
    function_call_id: Mapped[str | None] = mapped_column(String(255))
    llm_operation_id: Mapped[str | None] = mapped_column(String(36))
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    exchange_id: Mapped[str | None] = mapped_column(
        ForeignKey("exchanges.id", ondelete="SET NULL"), index=True
    )
    tool_version_id: Mapped[str | None] = mapped_column(ForeignKey("tool_versions.id"))
    binding_key: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(30), default="pending")
    arguments: Mapped[dict] = mapped_column(JSONB, default=dict)
    # Legacy final payload remains readable; new results have ordered child rows.
    result: Mapped[dict | list | str | int | float | bool | None] = mapped_column(
        JSONB(none_as_null=True)
    )
    connection_id: Mapped[str | None] = mapped_column(ForeignKey("integration_connections.id"))
    provider_message_id: Mapped[str | None] = mapped_column(String(255), index=True)
    receipts: Mapped[list] = mapped_column(JSONB, default=list)
    idempotency_key: Mapped[str] = mapped_column(String(120))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Callback(Identity, Created, Base):
    __tablename__ = "callbacks"
    contact_id: Mapped[str] = mapped_column(ForeignKey("contacts.id"), index=True)
    agent_version_id: Mapped[str] = mapped_column(ForeignKey("agent_versions.id"))
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    timezone: Mapped[str] = mapped_column(String(80))
    original_phrase: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="scheduled", index=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    call_id: Mapped[str | None] = mapped_column(ForeignKey("calls.id"))
