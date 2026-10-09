"""Hashed organization/user MCP tokens, limits and mutation audit."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0051_mcp_access"
down_revision = "0050_flat_contact_names"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "mcp_tokens",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("environment", sa.String(10), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_mcp_tokens_user_id", "mcp_tokens", ["user_id"])
    op.create_index("ix_mcp_tokens_organization_id", "mcp_tokens", ["organization_id"])
    op.create_table(
        "mcp_rate_buckets",
        sa.Column("key", sa.String(160), primary_key=True),
        sa.Column("window", sa.Integer(), primary_key=True),
        sa.Column("count", sa.Integer(), nullable=False),
    )
    op.create_table(
        "mcp_audit",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False
        ),
        sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_id", sa.String(36), sa.ForeignKey("mcp_tokens.id", ondelete="SET NULL")),
        sa.Column("operation", sa.String(160), nullable=False),
        sa.Column("outcome", sa.String(30), nullable=False),
        sa.Column("targets", postgresql.JSONB(), nullable=False),
    )
    op.create_index("ix_mcp_audit_organization_id", "mcp_audit", ["organization_id"])
    # Backend-only bootstrap tables, including on Supabase deployments.
    for table in ("mcp_tokens", "mcp_rate_buckets", "mcp_audit"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"REVOKE ALL ON {table} FROM PUBLIC")
        op.execute(f"""DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'voice_app') THEN
                GRANT ALL ON {table} TO voice_app;
                CREATE POLICY mcp_server_access ON {table} TO voice_app USING (true) WITH CHECK (true);
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN REVOKE ALL ON {table} FROM anon; END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN REVOKE ALL ON {table} FROM authenticated; END IF;
        END $$""")


def downgrade():
    for table in ("mcp_audit", "mcp_rate_buckets", "mcp_tokens"):
        op.drop_table(table)
