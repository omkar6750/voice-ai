"""Add transport_provider to runs and create browser_sessions table.

Revision ID: 0016_browser_sessions
Revises: 0015_twilio_telephony
Create Date: 2026-09-26
"""

import sqlalchemy as sa
from alembic import op

revision = "0016_browser_sessions"
down_revision = "0015_twilio_telephony"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "runs",
        sa.Column("transport_provider", sa.String(40), nullable=True),
    )
    op.create_table(
        "browser_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("runs.id"), nullable=False, unique=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="created"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disconnected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("connection_id", sa.String(255), nullable=True),
    )
    op.create_index(
        "ix_browser_sessions_run_id",
        "browser_sessions",
        ["run_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_browser_sessions_run_id", table_name="browser_sessions")
    op.drop_table("browser_sessions")
    op.drop_column("runs", "transport_provider")
