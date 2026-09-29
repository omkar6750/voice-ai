"""Add revocable, short-lived platform support sessions."""

import sqlalchemy as sa
from alembic import op

revision = "0038_platform_support_sessions"
down_revision = "0037_align_legacy_tenant_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_support_sessions",
        sa.Column("token_hash", sa.String(length=64), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "organization_id",
            sa.String(length=36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_platform_support_sessions_user_id", "platform_support_sessions", ["user_id"]
    )
    op.create_index(
        "ix_platform_support_sessions_organization_id",
        "platform_support_sessions",
        ["organization_id"],
    )
    op.create_index(
        "ix_platform_support_sessions_expires_at", "platform_support_sessions", ["expires_at"]
    )


def downgrade() -> None:
    op.drop_table("platform_support_sessions")
