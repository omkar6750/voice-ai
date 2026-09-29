from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .common import JSONB, Base, Created, Identity, OrganizationOwned, Updated, now


class IntegrationConnection(Identity, Updated, OrganizationOwned, Base):
    __tablename__ = "integration_connections"
    __table_args__ = (
        UniqueConstraint("org_id", "label", name="uq_integration_connections_org_label"),
    )
    label: Mapped[str] = mapped_column(String(120))
    provider: Mapped[str] = mapped_column(String(60))
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    enabled: Mapped[bool] = mapped_column(default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProviderCredential(Identity, Updated, OrganizationOwned, Base):
    """Encrypted AI-provider credential owned by exactly one organization."""

    __tablename__ = "provider_credentials"
    __table_args__ = (UniqueConstraint("org_id", "provider", name="uq_provider_credentials_org"),)
    provider: Mapped[str] = mapped_column(String(40))
    ciphertext: Mapped[str] = mapped_column(Text)
    key_id: Mapped[str] = mapped_column(String(80))
    updated_by_clerk_user_id: Mapped[str] = mapped_column(String(128))


class InboundWebhookMessage(Identity, Created, OrganizationOwned, Base):
    __tablename__ = "inbound_webhook_messages"
    __table_args__ = ()
    connection_id: Mapped[str | None] = mapped_column(
        ForeignKey("integration_connections.id", ondelete="SET NULL"), index=True
    )
    sender_phone: Mapped[str] = mapped_column(String(40), index=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(255))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)


class IntegrationSecret(Identity, OrganizationOwned, Base):
    __tablename__ = "integration_secrets"
    __table_args__ = (UniqueConstraint("connection_id", "name"),)
    connection_id: Mapped[str] = mapped_column(ForeignKey("integration_connections.id"))
    name: Mapped[str] = mapped_column(String(80))
    ciphertext: Mapped[str] = mapped_column(Text)
    key_id: Mapped[str] = mapped_column(String(80))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class IntegrationMedia(Identity, OrganizationOwned, Base):
    __tablename__ = "integration_media"
    __table_args__ = (UniqueConstraint("connection_id", "provider_media_id"),)
    connection_id: Mapped[str] = mapped_column(ForeignKey("integration_connections.id"))
    provider_media_id: Mapped[str] = mapped_column(String(120))
    display_name: Mapped[str] = mapped_column(String(255))
    filename: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(30))
    mime_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int]
    sha256: Mapped[str | None] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(30), default="uploaded")
    status: Mapped[str] = mapped_column(String(30), default="available")
    provider_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CalendarIntegration(Identity, Updated, OrganizationOwned, Base):
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


class CalendarIntegrationSecret(Identity, OrganizationOwned, Base):
    __tablename__ = "calendar_integration_secrets"
    __table_args__ = (UniqueConstraint("calendar_integration_id", "name"),)
    calendar_integration_id: Mapped[str] = mapped_column(
        ForeignKey("calendar_integrations.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(80))
    ciphertext: Mapped[str] = mapped_column(Text)
    key_id: Mapped[str] = mapped_column(String(80))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class CalendarOAuthState(Identity, OrganizationOwned, Base):
    __tablename__ = "calendar_oauth_states"
    state_hash: Mapped[str] = mapped_column(String(64), unique=True)
    calendar_integration_id: Mapped[str] = mapped_column(
        ForeignKey("calendar_integrations.id", ondelete="CASCADE"), index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pkce_verifier_ciphertext: Mapped[str | None] = mapped_column(Text)
    pkce_verifier_key_id: Mapped[str | None] = mapped_column(String(80))
