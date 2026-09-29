from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
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
    credential_id: Mapped[str | None] = mapped_column(ForeignKey("provider_credentials.id"), index=True)


class ProviderCredential(Identity, Updated, OrganizationOwned, Base):
    """Encrypted AI-provider credential owned by exactly one organization."""

    __tablename__ = "provider_credentials"
    __table_args__ = (
        Index("uq_provider_credentials_org_name", "org_id", "name", unique=True,
              postgresql_where=text("deleted_at IS NULL")),
        CheckConstraint("version > 0", name="ck_provider_credentials_version"),
        CheckConstraint("status IN ('stored', 'deleted')", name="ck_provider_credentials_status"),
    )
    provider: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(120))
    legacy_default: Mapped[bool] = mapped_column(default=False, server_default="false")
    purpose: Mapped[str] = mapped_column(String(40), default="api_key", server_default="api_key")
    version: Mapped[int] = mapped_column(default=1, server_default="1")
    status: Mapped[str] = mapped_column(String(20), default="stored", server_default="stored")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ciphertext: Mapped[str] = mapped_column(Text)
    key_id: Mapped[str] = mapped_column(String(80))
    updated_by_clerk_user_id: Mapped[str] = mapped_column(String(128))


class CredentialLease(Identity, Created, OrganizationOwned, Base):
    """Server-only run grant. No plaintext, ciphertext or browser bearer token."""

    __tablename__ = "credential_leases"
    __table_args__ = (
        CheckConstraint("credential_version > 0", name="ck_credential_leases_version"),
        UniqueConstraint("run_id", "credential_id", "credential_version", name="uq_credential_leases_run_version"),
    )
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    credential_id: Mapped[str] = mapped_column(ForeignKey("provider_credentials.id"), index=True)
    credential_version: Mapped[int]
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CallAdmission(Base):
    """One process-independent global runtime slot; internal control only."""

    __tablename__ = "call_admission"
    __table_args__ = (CheckConstraint("id = 1", name="ck_call_admission_singleton"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("runs.id", ondelete="SET NULL"))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


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
    version: Mapped[int] = mapped_column(default=1, server_default="1")
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
    version: Mapped[int] = mapped_column(default=1, server_default="1")
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
