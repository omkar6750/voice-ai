from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .common import JSONB, Base, Created, Identity, now


class Run(Identity, Created, Base):
    __tablename__ = "runs"
    __table_args__ = (
        Index("ix_runs_status_created", "status", "created_at"),
        CheckConstraint("channel IN ('phone','browser')", name="ck_run_channel"),
        Index(
            "uq_endpoint_active_run",
            "endpoint_id",
            unique=True,
            postgresql_where=text("status IN ('claimed','running','uncertain')"),
        ),
    )
    claim_token: Mapped[str | None] = mapped_column(String(36))
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    config_hash: Mapped[str | None] = mapped_column(String(64))
    snapshot_schema_version: Mapped[int | None]
    final_state: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    channel: Mapped[str] = mapped_column(String(20), default="phone", server_default="phone")
    transport_provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    contact_id: Mapped[str | None] = mapped_column(ForeignKey("contacts.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="queued")
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
    # Missing legacy creation timestamps stay unknown; new rows use DB time.
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=now, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider: Mapped[str] = mapped_column(String(40), default="sim7600", server_default="sim7600")
    provider_call_id: Mapped[str | None] = mapped_column(String(255))
    correlation_id: Mapped[str | None] = mapped_column(String(36), unique=True)
    provider_metadata: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    run_id: Mapped[str | None] = mapped_column(ForeignKey("runs.id"))
    contact_id: Mapped[str] = mapped_column(ForeignKey("contacts.id"), index=True)
    agent_version_id: Mapped[str] = mapped_column(ForeignKey("agent_versions.id"), index=True)
    target_snapshot: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="queued")
    modem_start: Mapped[dict] = mapped_column(JSONB, default=dict)
    modem_end: Mapped[dict] = mapped_column(JSONB, default=dict)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recording_path: Mapped[str | None] = mapped_column(String(500))
    telephony_connection_id: Mapped[str | None] = mapped_column(
        ForeignKey("integration_connections.id"), index=True
    )
    from_number: Mapped[str | None] = mapped_column(String(50))


class BrowserSession(Identity, Created, Base):
    __tablename__ = "browser_sessions"
    __table_args__ = (UniqueConstraint("run_id"),)

    # Missing legacy creation timestamps stay unknown; new rows use DB time.
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=now, server_default=func.now()
    )
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="created")
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    connection_id: Mapped[str | None] = mapped_column(String(255))


class Exchange(Identity, Created, Base):
    __tablename__ = "exchanges"
    __table_args__ = (
        UniqueConstraint("call_id", "sequence"),
        UniqueConstraint("run_id", "sequence"),
        UniqueConstraint("id", "run_id"),
    )
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    # Legacy linkage is preserved; new evidence uses run_id (ADR-0007).
    call_id: Mapped[str | None] = mapped_column(ForeignKey("calls.id", ondelete="CASCADE"))
    sequence: Mapped[int]
    origin: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(30), default="active")
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ConversationMessage(Identity, Created, Base):
    __tablename__ = "conversation_messages"
    __table_args__ = (
        Index("ix_conversation_messages_exchange_id_run_id", "exchange_id", "run_id"),
        UniqueConstraint("exchange_id", "sequence"),
        ForeignKeyConstraint(
            ["exchange_id", "run_id"],
            ["exchanges.id", "exchanges.run_id"],
            ondelete="CASCADE",
            name="fk_message_exchange_run",
        ),
    )
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    exchange_id: Mapped[str] = mapped_column(ForeignKey("exchanges.id", ondelete="CASCADE"))
    sequence: Mapped[int]
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    source_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    interrupted: Mapped[bool] = mapped_column(default=False)
    playback_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    playback_ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TraceSpan(Identity, Base):
    __tablename__ = "trace_spans"
    __table_args__ = (
        ForeignKeyConstraint(
            ["exchange_id", "run_id"],
            ["exchanges.id", "exchanges.run_id"],
            name="fk_span_exchange_run",
            deferrable=True,
            initially="DEFERRED",
        ),
        UniqueConstraint("id", "run_id"),
        ForeignKeyConstraint(
            ["parent_id", "run_id"],
            ["trace_spans.id", "trace_spans.run_id"],
            name="fk_span_parent_run",
        ),
        *(
            CheckConstraint(f"{name} IS NULL OR {name} >= 0", name=f"ck_span_{name}")
            for name in (
                "ttfb_ms",
                "ttfa_ms",
                "ttfat_ms",
                "audio_seconds",
                "prompt_tokens",
                "completion_tokens",
                "reasoning_tokens",
            )
        ),
    )
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
    parent_id: Mapped[str | None] = mapped_column(
        ForeignKey("trace_spans.id", ondelete="SET NULL"), index=True
    )
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
        ForeignKeyConstraint(
            ["exchange_id", "run_id"],
            ["exchanges.id", "exchanges.run_id"],
            name="fk_tool_exchange_run",
            deferrable=True,
            initially="DEFERRED",
        ),
        Index("ix_tool_llm_operation", "llm_operation_id"),
        Index("ix_tool_provider_receipt", "connection_id", "provider_message_id"),
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
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    exchange_id: Mapped[str | None] = mapped_column(
        ForeignKey("exchanges.id", ondelete="SET NULL"), index=True
    )
    tool_version_id: Mapped[str | None] = mapped_column(ForeignKey("tool_versions.id"), index=True)
    binding_key: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(30), default="pending")
    arguments: Mapped[dict] = mapped_column(JSONB, default=dict)
    # Legacy final payload remains readable; new results have ordered child rows.
    result: Mapped[dict | list | str | int | float | bool | None] = mapped_column(
        JSONB(none_as_null=True)
    )
    connection_id: Mapped[str | None] = mapped_column(
        ForeignKey("integration_connections.id"), index=True
    )
    provider_message_id: Mapped[str | None] = mapped_column(String(255))
    receipts: Mapped[list] = mapped_column(JSONB, default=list)
    idempotency_key: Mapped[str] = mapped_column(String(120))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Callback(Identity, Created, Base):
    __tablename__ = "callbacks"
    __table_args__ = (
        Index(
            "ix_callbacks_due_scheduled", "due_at", postgresql_where=text("status = 'scheduled'")
        ),
        CheckConstraint("automatic_attempts BETWEEN 0 AND 1", name="ck_callback_one_auto_attempt"),
    )
    request_key: Mapped[str | None] = mapped_column(String(120), unique=True)
    claim_token: Mapped[str | None] = mapped_column(String(36))
    automatic_attempts: Mapped[int] = mapped_column(default=0, server_default="0")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    contact_id: Mapped[str] = mapped_column(ForeignKey("contacts.id"), index=True)
    agent_version_id: Mapped[str] = mapped_column(ForeignKey("agent_versions.id"), index=True)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    timezone: Mapped[str] = mapped_column(String(80))
    original_phrase: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="scheduled")
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    call_id: Mapped[str | None] = mapped_column(ForeignKey("calls.id"), index=True)
    callback_mode: Mapped[str] = mapped_column(
        String(20), default="automatic", server_default="automatic"
    )
    requested_window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    requested_window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scheduled_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scheduled_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    role_key: Mapped[str | None] = mapped_column(String(100))
    bookable_person_key: Mapped[str | None] = mapped_column(String(120))
    calendar_integration_id: Mapped[str | None] = mapped_column(
        ForeignKey("calendar_integrations.id"), index=True
    )
    calendar_event_id: Mapped[str | None] = mapped_column(String(255))
    reason: Mapped[str | None] = mapped_column(Text)
