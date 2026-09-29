from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from voice_api.db.base_class import Base


def new_id() -> str:
    return str(uuid4())


def now() -> datetime:
    return datetime.now(UTC)


class Identity:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)


class OrganizationOwned:
    """Tenant-owned records must always belong to exactly one organization."""

    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True, nullable=False)


class Created:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now, server_default=func.now()
    )


class Updated(Created):
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


__all__ = ["JSONB", "Base", "Created", "Identity", "Updated", "new_id", "now"]
