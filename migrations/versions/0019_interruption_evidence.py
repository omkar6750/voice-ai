"""Persist interruption causes and explicit operation output states."""

import sqlalchemy as sa
from alembic import op

revision = "0019_interruption_evidence"
down_revision = "0018_classifier_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "interruption_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "run_id", sa.String(36), sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("exchange_id", sa.String(36)),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("reason", sa.String(255), nullable=False),
        sa.Column("frame_type", sa.String(120), nullable=False),
        sa.Column("interrupted_operation_ids", sa.JSON(), nullable=False),
        sa.Column("interrupted_tool_invocation_ids", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "source IN ('caller','system','transport')", name="ck_interruption_event_source"
        ),
    )
    for column in ("run_id", "exchange_id"):
        op.create_index(f"ix_interruption_events_{column}", "interruption_events", [column])

    op.add_column(
        "trace_spans",
        sa.Column("output_state", sa.String(20), nullable=False, server_default="not_recorded"),
    )
    op.add_column("trace_spans", sa.Column("interruption_id", sa.String(36)))
    op.create_index("ix_trace_spans_interruption_id", "trace_spans", ["interruption_id"])
    op.add_column("tool_invocations", sa.Column("interruption_id", sa.String(36)))
    op.create_index(
        "ix_tool_invocations_interruption_id", "tool_invocations", ["interruption_id"]
    )


def downgrade() -> None:
    raise RuntimeError("Interruption evidence must not be removed without a reviewed migration")
