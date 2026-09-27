"""Persist automatic classifier results and their context delivery."""

import sqlalchemy as sa
from alembic import op

revision = "0018_classifier_evidence"
down_revision = "0017_tool_context_delivery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "classifier_results",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "run_id", sa.String(36), sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "operation_id",
            sa.String(36),
            sa.ForeignKey("trace_spans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("phase", sa.String(10), nullable=False),
        sa.Column("node_key", sa.String(120), nullable=False),
        sa.Column("classifier_type", sa.String(10), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("result", sa.JSON()),
        sa.Column("error", sa.String(500)),
        sa.Column("transcript_sha256", sa.String(64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("operation_id"),
        sa.CheckConstraint("phase IN ('entry','exit')", name="ck_classifier_result_phase"),
        sa.CheckConstraint(
            "classifier_type IN ('llm','jev')", name="ck_classifier_result_type"
        ),
        sa.CheckConstraint(
            "status IN ('completed','failed')", name="ck_classifier_result_status"
        ),
    )
    for column in ("run_id", "operation_id"):
        op.create_index(f"ix_classifier_results_{column}", "classifier_results", [column])

    op.create_table(
        "classifier_context_deliveries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "run_id", sa.String(36), sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "classifier_result_id",
            sa.String(36),
            sa.ForeignKey("classifier_results.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "operation_id",
            sa.String(36),
            sa.ForeignKey("trace_spans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("phase", sa.String(10), nullable=False),
        sa.Column("node_key", sa.String(120), nullable=False),
        sa.Column("status", sa.String(40), nullable=False, server_default="delivered"),
        sa.Column("context_message_index", sa.Integer(), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("consumed_exchange_id", sa.String(36)),
        sa.Column("consuming_operation_id", sa.String(36)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("classifier_result_id"),
        sa.CheckConstraint(
            "status IN ('delivered','consumed','interrupted_before_consumption')",
            name="ck_classifier_context_delivery_status",
        ),
        sa.CheckConstraint(
            "context_message_index >= 0", name="ck_classifier_context_delivery_index"
        ),
    )
    for column in (
        "run_id",
        "classifier_result_id",
        "operation_id",
        "consumed_exchange_id",
        "consuming_operation_id",
    ):
        op.create_index(
            f"ix_classifier_context_deliveries_{column}",
            "classifier_context_deliveries",
            [column],
        )


def downgrade() -> None:
    raise RuntimeError("Classifier evidence must not be removed without a reviewed migration")
