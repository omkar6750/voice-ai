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
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .common import JSONB, Base, Created, Identity


class FlowNodeVisit(Identity, Created, Base):
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


class ToolInvocationResult(Identity, Created, Base):
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
