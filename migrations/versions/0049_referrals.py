"""Capture pending referrals independently from dialable contacts and run evidence."""

import sqlalchemy as sa
from alembic import op

revision = "0049_referrals"
down_revision = "0048_contact_name_parts"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "referrals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "referrer_contact_id", sa.String(36), sa.ForeignKey("contacts.id", ondelete="SET NULL")
        ),
        sa.Column("source_run_id", sa.String(36), sa.ForeignKey("runs.id", ondelete="SET NULL")),
        sa.Column(
            "promoted_contact_id", sa.String(36), sa.ForeignKey("contacts.id", ondelete="SET NULL")
        ),
        sa.Column("source_invocation_id", sa.String(120), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("first_name", sa.String(120), nullable=False),
        sa.Column("last_name", sa.String(120)),
        sa.Column("phone_number", sa.String(80)),
        sa.Column("email", sa.String(254)),
        sa.Column("organization", sa.String(240)),
        sa.Column("role", sa.String(240)),
        sa.Column("context", sa.Text),
        sa.Column(
            "contact_details_confirmed", sa.Boolean, nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "phone_verification_status", sa.String(20), nullable=False, server_default="unverified"
        ),
        sa.Column(
            "email_verification_status", sa.String(20), nullable=False, server_default="unverified"
        ),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending_review"),
        sa.UniqueConstraint("org_id", "source_invocation_id", name="uq_referrals_org_invocation"),
        sa.CheckConstraint(
            "status IN ('pending_review','reviewed','dismissed','converted')",
            name="ck_referral_status",
        ),
        sa.CheckConstraint(
            "phone_verification_status IN ('unverified','verified')",
            name="ck_referral_phone_verification",
        ),
        sa.CheckConstraint(
            "email_verification_status IN ('unverified','verified')",
            name="ck_referral_email_verification",
        ),
    )
    op.create_index("ix_referrals_org_id", "referrals", ["org_id"])
    op.create_index("ix_referrals_org_created_id", "referrals", ["org_id", "created_at", "id"])
    for column, parent in (
        ("referrer_contact_id", "contacts"),
        ("source_run_id", "runs"),
        ("promoted_contact_id", "contacts"),
    ):
        op.create_index(f"ix_referrals_{column}", "referrals", [column])
        op.execute(
            f"CREATE TRIGGER referrals_{column}_org BEFORE INSERT OR UPDATE ON referrals FOR EACH ROW EXECUTE FUNCTION enforce_same_org_reference('{parent}','id','{column}','referrals_{column}_fkey')"
        )
    # Supabase can grant new tables to browser roles through default privileges.
    # Only the server login accesses caller-provided referral details.
    op.execute("ALTER TABLE referrals ENABLE ROW LEVEL SECURITY")
    op.execute("REVOKE ALL ON TABLE referrals FROM PUBLIC")
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
                REVOKE ALL ON TABLE referrals FROM anon;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                REVOKE ALL ON TABLE referrals FROM authenticated;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'voice_app') THEN
                GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE referrals TO voice_app;
                CREATE POLICY voice_api_server_access ON referrals FOR ALL TO voice_app USING (true) WITH CHECK (true);
            END IF;
        END $$
    """)


def downgrade():
    op.drop_table("referrals")
