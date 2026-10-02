"""Persist independent runtime ownership and tool attempt fences."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0044_separate_runtime"
down_revision = "0043_remote_artifact_guard"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "runtime_assignments",
        sa.Column(
            "run_id", sa.String(36), sa.ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("generation", sa.String(36), nullable=False),
        sa.Column("boot_id", sa.String(36)),
        sa.Column("grant_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(30), nullable=False),
        sa.Column("metrics", JSONB, nullable=False),
        sa.Column("diagnostic_sequence", sa.Integer, nullable=False),
    )
    op.create_index("ix_runtime_assignments_org_id", "runtime_assignments", ["org_id"])
    op.create_table(
        "runtime_tool_attempts",
        sa.Column("invocation_id", sa.String(36), primary_key=True),
        sa.Column(
            "run_id", sa.String(36), sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("state", sa.String(30), nullable=False),
        sa.Column("result", JSONB),
    )
    op.create_index("ix_runtime_tool_attempts_run_id", "runtime_tool_attempts", ["run_id"])


def downgrade():
    op.drop_table("runtime_tool_attempts")
    op.drop_table("runtime_assignments")
