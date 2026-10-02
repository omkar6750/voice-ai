"""Durable runtime ownership and external tool attempt fences."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from .common import JSONB, Base, OrganizationOwned


class RuntimeAssignment(OrganizationOwned, Base):
    __tablename__ = "runtime_assignments"
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    generation: Mapped[str] = mapped_column(String(36))
    boot_id: Mapped[str | None] = mapped_column(String(36))
    grant_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    state: Mapped[str] = mapped_column(String(30), default="preparing")
    metrics: Mapped[dict] = mapped_column(JSONB, default=dict)
    diagnostic_sequence: Mapped[int] = mapped_column(default=0)


class RuntimeToolAttempt(Base):
    __tablename__ = "runtime_tool_attempts"
    invocation_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(30))
    result: Mapped[dict | None] = mapped_column(JSONB)
