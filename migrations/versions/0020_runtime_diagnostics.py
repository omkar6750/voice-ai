"""Persist normalized runtime, provider, modem, and termination diagnostics."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0020_runtime_diagnostics"
down_revision = "0019_interruption_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "run_diagnostics",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "run_id", sa.String(36), sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("severity", sa.String(10), nullable=False),
        sa.Column("category", sa.String(80), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("code", sa.String(120)),
        sa.Column("message", sa.String(500), nullable=False),
        sa.Column("detail", sa.Text()),
        sa.Column("retryable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("uncertain", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("provider_request_id", sa.String(255)),
        sa.Column("http_status", sa.Integer()),
        sa.Column("retry_after_seconds", sa.Float()),
        sa.Column("metadata", JSONB(), nullable=False, server_default="{}"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "severity IN ('info','warning','error')", name="ck_run_diagnostic_severity"
        ),
        sa.CheckConstraint(
            "source IN ('provider','modem','transport','call','evidence','runtime')",
            name="ck_run_diagnostic_source",
        ),
        sa.CheckConstraint(
            "http_status IS NULL OR http_status BETWEEN 100 AND 599",
            name="ck_run_diagnostic_http_status",
        ),
        sa.CheckConstraint(
            "retry_after_seconds IS NULL OR retry_after_seconds >= 0",
            name="ck_run_diagnostic_retry_after",
        ),
    )
    op.create_index("ix_run_diagnostics_run_id", "run_diagnostics", ["run_id"])
    op.create_index("ix_run_diagnostics_occurred_at", "run_diagnostics", ["occurred_at"])


def downgrade() -> None:
    raise RuntimeError("Runtime diagnostics must not be removed without a reviewed migration")
