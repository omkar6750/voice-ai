from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .common import JSONB, Base, Identity, Updated, now


class IntegrationConnection(Identity, Updated, Base):
    __tablename__ = "integration_connections"
    label: Mapped[str] = mapped_column(String(120), unique=True)
    provider: Mapped[str] = mapped_column(String(60))
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    enabled: Mapped[bool] = mapped_column(default=False)


class IntegrationSecret(Identity, Base):
    __tablename__ = "integration_secrets"
    __table_args__ = (UniqueConstraint("connection_id", "name"),)
    connection_id: Mapped[str] = mapped_column(ForeignKey("integration_connections.id"))
    name: Mapped[str] = mapped_column(String(80))
    ciphertext: Mapped[str] = mapped_column(Text)
    key_id: Mapped[str] = mapped_column(String(80))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class IntegrationMedia(Identity, Base):
    __tablename__ = "integration_media"
    __table_args__ = (UniqueConstraint("connection_id", "provider_media_id"),)
    connection_id: Mapped[str] = mapped_column(ForeignKey("integration_connections.id"))
    provider_media_id: Mapped[str] = mapped_column(String(120))
    filename: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int]
    sha256: Mapped[str] = mapped_column(String(64))
    source_path: Mapped[str | None] = mapped_column(Text)
    availability: Mapped[str] = mapped_column(String(30), default="available")
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
