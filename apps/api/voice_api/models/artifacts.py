"""Recording storage and durable, explicitly requested deletion."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .common import JSONB, Base, Created, Identity, OrganizationOwned


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
    storage_backend: Mapped[str] = mapped_column(
        String(20), default="local", server_default="local"
    )
    storage_status: Mapped[str] = mapped_column(
        String(20), default="available", server_default="available"
    )
    vendor_public_id: Mapped[str | None] = mapped_column(Text, unique=True)
    vendor_asset_id: Mapped[str | None] = mapped_column(Text)
    vendor_version: Mapped[int | None] = mapped_column(BigInteger)
    vendor_format: Mapped[str | None] = mapped_column(String(30))
    storage_error: Mapped[str | None] = mapped_column(Text)
    deletion_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RecordingDeletion(Identity, Created, OrganizationOwned, Base):
    __tablename__ = "recording_deletions"
    actor_id: Mapped[str] = mapped_column(String(255))
    confirmation_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    scope: Mapped[str] = mapped_column(String(30))
    snapshot: Mapped[list] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), default="preview")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RecordingDeletionItem(Identity, Created, OrganizationOwned, Base):
    __tablename__ = "recording_deletion_items"
    __table_args__ = (UniqueConstraint("operation_id", "artifact_id"),)
    operation_id: Mapped[str] = mapped_column(ForeignKey("recording_deletions.id"), index=True)
    # Audit identity survives subsequent hard deletion of a fully deleted run.
    artifact_id: Mapped[str] = mapped_column(String(36), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    error: Mapped[str | None] = mapped_column(Text)
