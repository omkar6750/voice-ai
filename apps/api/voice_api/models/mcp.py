"""Hashed user capabilities; these bootstrap records never grant membership."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .common import JSONB, Base, Created, Identity


class McpToken(Identity, Created, Base):
    __tablename__ = "mcp_tokens"

    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(80))
    environment: Mapped[str] = mapped_column(String(10))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class McpRateBucket(Base):
    __tablename__ = "mcp_rate_buckets"

    key: Mapped[str] = mapped_column(String(160), primary_key=True)
    window: Mapped[int] = mapped_column(Integer, primary_key=True)
    count: Mapped[int] = mapped_column(Integer)


class McpAudit(Identity, Created, Base):
    __tablename__ = "mcp_audit"

    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    actor_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    token_id: Mapped[str | None] = mapped_column(ForeignKey("mcp_tokens.id", ondelete="SET NULL"))
    operation: Mapped[str] = mapped_column(String(160))
    outcome: Mapped[str] = mapped_column(String(30))
    targets: Mapped[dict] = mapped_column(JSONB, default=dict)
