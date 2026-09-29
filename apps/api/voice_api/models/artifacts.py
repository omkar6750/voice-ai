"""Expiring call files, separate from reusable integration media."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .common import Base, Created, Identity, OrganizationOwned


class RunArtifact(Identity, Created, OrganizationOwned, Base):
    __tablename__ = "run_artifacts"
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    path: Mapped[str] = mapped_column(Text, unique=True)
    sha256: Mapped[str | None] = mapped_column(String(64))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    sample_rate: Mapped[int | None]
    channels: Mapped[int | None]
    sample_width: Mapped[int | None]
    duration_seconds: Mapped[float | None]
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deletion_error: Mapped[str | None] = mapped_column(Text)
