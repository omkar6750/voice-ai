"""Append-only derived evidence with explicit source boundaries and supersession."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .common import JSONB, Base, Created, Identity, OrganizationOwned


class Classification(Identity, Created, OrganizationOwned, Base):
    __tablename__ = "classifications"
    __table_args__ = (
        ForeignKeyConstraint(["operation_id", "run_id"], ["trace_spans.id", "trace_spans.run_id"]),
        CheckConstraint("confidence IS NULL OR confidence BETWEEN 0 AND 1"),
        CheckConstraint(
            "(status = 'completed' AND verdict IS NOT NULL) OR (status = 'failed' AND verdict IS NULL)"
        ),
    )
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    operation_id: Mapped[str] = mapped_column(String(36))
    source_message_ids: Mapped[list] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20))
    verdict: Mapped[str | None] = mapped_column(String(40))
    confidence: Mapped[float | None]
    evidence: Mapped[dict] = mapped_column(JSONB)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ContextSummary(Identity, Created, OrganizationOwned, Base):
    __tablename__ = "context_summaries"
    __table_args__ = (
        ForeignKeyConstraint(["operation_id", "run_id"], ["trace_spans.id", "trace_spans.run_id"]),
    )
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    operation_id: Mapped[str] = mapped_column(String(36))
    source_message_ids: Mapped[list] = mapped_column(JSONB)
    content: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ContactFact(Identity, Created, OrganizationOwned, Base):
    __tablename__ = "contact_facts"
    contact_id: Mapped[str] = mapped_column(ForeignKey("contacts.id"), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    value: Mapped[dict | list | str | int | float | bool | None] = mapped_column(
        JSONB, nullable=False
    )
    source_message_ids: Mapped[list] = mapped_column(JSONB)
    supersedes_id: Mapped[str | None] = mapped_column(ForeignKey("contact_facts.id"), unique=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
