"""Pending referrals survive conversation and contact cleanup."""

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .common import Base, Identity, OrganizationOwned, Updated


class Referral(Identity, Updated, OrganizationOwned, Base):
    __tablename__ = "referrals"
    __table_args__ = (
        UniqueConstraint("org_id", "source_invocation_id", name="uq_referrals_org_invocation"),
        CheckConstraint(
            "status IN ('pending_review','reviewed','dismissed','converted')",
            name="ck_referral_status",
        ),
        CheckConstraint(
            "phone_verification_status IN ('unverified','verified')",
            name="ck_referral_phone_verification",
        ),
        CheckConstraint(
            "email_verification_status IN ('unverified','verified')",
            name="ck_referral_email_verification",
        ),
        Index("ix_referrals_org_created_id", "org_id", "created_at", "id"),
    )
    referrer_contact_id: Mapped[str | None] = mapped_column(
        ForeignKey("contacts.id", ondelete="SET NULL"), index=True
    )
    source_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("runs.id", ondelete="SET NULL"), index=True
    )
    promoted_contact_id: Mapped[str | None] = mapped_column(
        ForeignKey("contacts.id", ondelete="SET NULL"), index=True
    )
    source_invocation_id: Mapped[str] = mapped_column(String(120))
    request_hash: Mapped[str] = mapped_column(String(64))
    first_name: Mapped[str] = mapped_column(String(120))
    last_name: Mapped[str | None] = mapped_column(String(120))
    phone_number: Mapped[str | None] = mapped_column(String(80))
    email: Mapped[str | None] = mapped_column(String(254))
    organization: Mapped[str | None] = mapped_column(String(240))
    role: Mapped[str | None] = mapped_column(String(240))
    context: Mapped[str | None] = mapped_column(Text)
    contact_details_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    phone_verification_status: Mapped[str] = mapped_column(String(20), default="unverified")
    email_verification_status: Mapped[str] = mapped_column(String(20), default="unverified")
    status: Mapped[str] = mapped_column(String(30), default="pending_review")
