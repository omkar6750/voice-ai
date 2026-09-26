from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .common import JSONB, Base, Created, Identity, Updated, now


class IntegrationConnection(Identity, Updated, Base):
    __tablename__ = "integration_connections"
    __table_args__ = ()
    label: Mapped[str] = mapped_column(String(120), unique=True)
    provider: Mapped[str] = mapped_column(String(60))
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    enabled: Mapped[bool] = mapped_column(default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InboundWebhookMessage(Identity, Created, Base):
    __tablename__ = "inbound_webhook_messages"
    __table_args__ = ()
    connection_id: Mapped[str | None] = mapped_column(
        ForeignKey("integration_connections.id", ondelete="SET NULL"), index=True
    )
    sender_phone: Mapped[str] = mapped_column(String(40), index=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(255))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)


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


class CalendarIntegration(Identity, Updated, Base):
    __tablename__ = "calendar_integrations"
    provider: Mapped[str] = mapped_column(String(40), default="google_calendar")
    display_name: Mapped[str] = mapped_column(String(120))
    calendar_id: Mapped[str] = mapped_column(String(120), default="primary")
    timezone: Mapped[str] = mapped_column(String(80), default="UTC")
    scopes: Mapped[list] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)


class CalendarIntegrationSecret(Identity, Base):
    __tablename__ = "calendar_integration_secrets"
    __table_args__ = (UniqueConstraint("calendar_integration_id", "name"),)
    calendar_integration_id: Mapped[str] = mapped_column(
        ForeignKey("calendar_integrations.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(80))
    ciphertext: Mapped[str] = mapped_column(Text)
    key_id: Mapped[str] = mapped_column(String(80))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class CalendarOAuthState(Identity, Base):
    __tablename__ = "calendar_oauth_states"
    state_hash: Mapped[str] = mapped_column(String(64), unique=True)
    calendar_integration_id: Mapped[str] = mapped_column(
        ForeignKey("calendar_integrations.id", ondelete="CASCADE"), index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pkce_verifier_ciphertext: Mapped[str | None] = mapped_column(Text)
    pkce_verifier_key_id: Mapped[str | None] = mapped_column(String(80))
