"""Local identity projection and customer organization catalog.

Clerk remains the source of truth for sign-in and organization membership.
These tables do not, by themselves, grant access to tenant resources.
"""

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from .common import Base, Identity, Updated


class User(Identity, Updated, Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("clerk_user_id"),)

    clerk_user_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    primary_verified_email: Mapped[str | None] = mapped_column(String(320))
    first_name: Mapped[str | None] = mapped_column(String(120))
    last_name: Mapped[str | None] = mapped_column(String(120))
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Organization(Identity, Updated, Base):
    __tablename__ = "organizations"
    __table_args__ = (
        UniqueConstraint("clerk_org_id"),
        UniqueConstraint("owner_user_id", name="uq_organizations_owner_user_id"),
    )

    clerk_org_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    seed_manifest_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class OrganizationCreationClaim(Base):
    __tablename__ = "organization_creation_claims"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    organization_id: Mapped[str | None] = mapped_column(ForeignKey("organizations.id"), unique=True)


class PlatformAdministrator(Base):
    """Single local platform assignment; Clerk alone cannot grant this role."""

    __tablename__ = "platform_administrator"
    __table_args__ = (CheckConstraint("id = 1", name="ck_platform_administrator_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), unique=True)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PlatformSupportSession(Base):
    """Short-lived, explicitly started platform-admin access to one org."""

    __tablename__ = "platform_support_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LegacyDataTenant(Base):
    """Temporary stable mapping for unscoped records during tenant migration."""

    __tablename__ = "legacy_data_tenant"
    __table_args__ = (CheckConstraint("id = 1", name="ck_legacy_data_tenant_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), unique=True)


class OrganizationAudit(Identity, Base):
    __tablename__ = "organization_audit"

    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    actor_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    target_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClerkWebhookEvent(Base):
    """Replay ledger for verified Clerk webhook deliveries."""

    __tablename__ = "clerk_webhook_events"

    event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
