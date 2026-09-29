"""Flow visit identity and ordered tool evidence; timing belongs to spans (ADR-0007)."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .common import JSONB, Base, Created, Identity, OrganizationOwned


class FlowNodeVisit(Identity, Created, OrganizationOwned, Base):
    __tablename__ = "flow_node_visits"
    __table_args__ = (
        UniqueConstraint("run_id", "sequence"),
        UniqueConstraint("span_id"),
        CheckConstraint("sequence > 0"),
        ForeignKeyConstraint(
            ["span_id", "run_id"],
            ["trace_spans.id", "trace_spans.run_id"],
            name="fk_visit_span_run",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["triggered_by_tool_id", "run_id"],
            ["tool_invocations.id", "tool_invocations.run_id"],
            name="fk_visit_tool_run",
        ),
    )
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int]
    node_key: Mapped[str] = mapped_column(String(120))
    span_id: Mapped[str] = mapped_column(String(36))
    triggered_by_tool_id: Mapped[str | None] = mapped_column(String(36), index=True)


class ToolInvocationResult(Identity, Created, OrganizationOwned, Base):
    __tablename__ = "tool_invocation_results"
    __table_args__ = (
        UniqueConstraint("tool_invocation_id", "sequence"),
        CheckConstraint("sequence > 0"),
        CheckConstraint("(consumed_at IS NULL) = (consumed_exchange_id IS NULL)"),
        ForeignKeyConstraint(
            ["tool_invocation_id", "run_id"],
            ["tool_invocations.id", "tool_invocations.run_id"],
            name="fk_result_tool_run",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["consumed_exchange_id", "run_id"],
            ["exchanges.id", "exchanges.run_id"],
            name="fk_result_consumption_run",
        ),
        Index(
            "uq_tool_final_result",
            "tool_invocation_id",
            unique=True,
            postgresql_where=text("is_final"),
        ),
    )
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    tool_invocation_id: Mapped[str] = mapped_column(String(36), index=True)
    sequence: Mapped[int]
    payload: Mapped[Any] = mapped_column(JSONB, nullable=False)
    is_final: Mapped[bool]
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consumed_exchange_id: Mapped[str | None] = mapped_column(String(36), index=True)


class ToolContextDelivery(Identity, Created, OrganizationOwned, Base):
    """Proof that a result entered context and, optionally, which LLM consumed it."""

    __tablename__ = "tool_context_deliveries"
    __table_args__ = (
        UniqueConstraint("result_id"),
        CheckConstraint(
            "status IN ('delivered','consumed','context_update_failed','interrupted_before_consumption')"
        ),
        CheckConstraint("context_message_index IS NULL OR context_message_index >= 0"),
    )
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    tool_invocation_id: Mapped[str] = mapped_column(
        ForeignKey("tool_invocations.id", ondelete="CASCADE"), index=True
    )
    result_id: Mapped[str] = mapped_column(
        ForeignKey("tool_invocation_results.id", ondelete="CASCADE"), index=True
    )
    function_call_id: Mapped[str | None] = mapped_column(String(255))
    is_final: Mapped[bool]
    status: Mapped[str] = mapped_column(String(40), default="delivered")
    context_message_index: Mapped[int | None]
    delivered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consumed_exchange_id: Mapped[str | None] = mapped_column(String(36), index=True)
    consuming_span_id: Mapped[str | None] = mapped_column(String(36), index=True)


class ClassifierResult(Identity, Created, OrganizationOwned, Base):
    """The finalized result of an automatic entry or exit classifier run."""

    __tablename__ = "classifier_results"
    __table_args__ = (
        UniqueConstraint("operation_id"),
        CheckConstraint("phase IN ('entry','exit')"),
        CheckConstraint("classifier_type IN ('llm','jev')"),
        CheckConstraint("status IN ('completed','failed')"),
    )
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    operation_id: Mapped[str] = mapped_column(
        ForeignKey("trace_spans.id", ondelete="CASCADE"), index=True
    )
    phase: Mapped[str] = mapped_column(String(10))
    node_key: Mapped[str] = mapped_column(String(120))
    classifier_type: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20))
    result: Mapped[dict | list | str | int | float | bool | None] = mapped_column(
        JSONB(none_as_null=True)
    )
    error: Mapped[str | None] = mapped_column(String(500))
    transcript_sha256: Mapped[str] = mapped_column(String(64))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ClassifierContextDelivery(Identity, Created, OrganizationOwned, Base):
    """Proof that a classifier result reached a subsequent LLM context."""

    __tablename__ = "classifier_context_deliveries"
    __table_args__ = (
        UniqueConstraint("classifier_result_id"),
        CheckConstraint("status IN ('delivered','consumed','interrupted_before_consumption')"),
        CheckConstraint("context_message_index >= 0"),
    )
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    classifier_result_id: Mapped[str] = mapped_column(
        ForeignKey("classifier_results.id", ondelete="CASCADE"), index=True
    )
    operation_id: Mapped[str] = mapped_column(
        ForeignKey("trace_spans.id", ondelete="CASCADE"), index=True
    )
    phase: Mapped[str] = mapped_column(String(10))
    node_key: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(40), default="delivered")
    context_message_index: Mapped[int]
    delivered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consumed_exchange_id: Mapped[str | None] = mapped_column(String(36), index=True)
    consuming_operation_id: Mapped[str | None] = mapped_column(String(36), index=True)


class RunContextEvent(Identity, Created, OrganizationOwned, Base):
    """Durable asynchronous outcome queued for the next caller-driven inference."""

    __tablename__ = "run_context_events"
    __table_args__ = (
        UniqueConstraint("run_id", "dedupe_key", name="uq_run_context_event_dedupe"),
        CheckConstraint(
            "status IN ('pending','delivered','consumed','ended_before_delivery')",
            name="ck_run_context_event_status",
        ),
        CheckConstraint(
            "source IN ('tool_result','whatsapp_receipt')",
            name="ck_run_context_event_source",
        ),
        CheckConstraint(
            "context_message_index IS NULL OR context_message_index >= 0",
            name="ck_run_context_event_index",
        ),
        Index("ix_run_context_event_pending", "run_id", "status", "occurred_at"),
        Index("ix_run_context_event_provider_message", "connection_id", "provider_message_id"),
    )
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    # A tool invocation's finalized evidence may still be in the local spool
    # when an outcome is produced, so this is a soft run-scoped source reference.
    tool_invocation_id: Mapped[str | None] = mapped_column(String(36), index=True)
    dedupe_key: Mapped[str] = mapped_column(String(255))
    source: Mapped[str] = mapped_column(String(40))
    source_reference: Mapped[str | None] = mapped_column(String(255))
    connection_id: Mapped[str | None] = mapped_column(String(36))
    provider_message_id: Mapped[str | None] = mapped_column(String(255))
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="pending")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    context_message_index: Mapped[int | None]
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consumed_exchange_id: Mapped[str | None] = mapped_column(String(36))
    consuming_span_id: Mapped[str | None] = mapped_column(String(36))


class InterruptionEvent(Identity, Created, OrganizationOwned, Base):
    """Causal interruption marker linking a frame to cancelled work."""

    __tablename__ = "interruption_events"
    __table_args__ = (CheckConstraint("source IN ('caller','system','transport')"),)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    exchange_id: Mapped[str | None] = mapped_column(String(36), index=True)
    source: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(String(255))
    frame_type: Mapped[str] = mapped_column(String(120))
    interrupted_operation_ids: Mapped[list] = mapped_column(JSONB, default=list)
    interrupted_tool_invocation_ids: Mapped[list] = mapped_column(JSONB, default=list)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RunDiagnostic(Identity, Created, OrganizationOwned, Base):
    __tablename__ = "run_diagnostics"
    __table_args__ = (
        Index("ix_run_diagnostics_occurred_at", "occurred_at"),
        CheckConstraint("severity IN ('info','warning','error')"),
        CheckConstraint("source IN ('provider','modem','transport','call','evidence','runtime')"),
        CheckConstraint("http_status IS NULL OR http_status BETWEEN 100 AND 599"),
        CheckConstraint("retry_after_seconds IS NULL OR retry_after_seconds >= 0"),
    )
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    severity: Mapped[str] = mapped_column(String(10))
    category: Mapped[str] = mapped_column(String(80))
    source: Mapped[str] = mapped_column(String(20))
    code: Mapped[str | None] = mapped_column(String(120))
    message: Mapped[str] = mapped_column(String(500))
    detail: Mapped[str | None] = mapped_column(Text)
    retryable: Mapped[bool] = mapped_column(default=False, server_default="false")
    uncertain: Mapped[bool] = mapped_column(default=False, server_default="false")
    provider_request_id: Mapped[str | None] = mapped_column(String(255))
    http_status: Mapped[int | None]
    retry_after_seconds: Mapped[float | None]
    metadata_json: Mapped[dict] = mapped_column(
        "metadata", JSONB, default=dict, server_default="{}"
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
