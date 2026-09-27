"""Persist explicit tool-result context delivery and consumption provenance."""

import sqlalchemy as sa
from alembic import op

revision = "0017_tool_context_delivery"
down_revision = "0016_browser_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tool_context_deliveries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "run_id", sa.String(36), sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "tool_invocation_id",
            sa.String(36),
            sa.ForeignKey("tool_invocations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "result_id",
            sa.String(36),
            sa.ForeignKey("tool_invocation_results.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("function_call_id", sa.String(255)),
        sa.Column("is_final", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False, server_default="delivered"),
        sa.Column("context_message_index", sa.Integer()),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("consumed_exchange_id", sa.String(36)),
        sa.Column("consuming_span_id", sa.String(36)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("result_id"),
        sa.CheckConstraint(
            "status IN ('delivered','consumed','context_update_failed','interrupted_before_consumption')",
            name="ck_tool_context_delivery_status",
        ),
        sa.CheckConstraint(
            "context_message_index IS NULL OR context_message_index >= 0",
            name="ck_tool_context_delivery_index",
        ),
    )
    for column in ("run_id", "tool_invocation_id", "result_id", "consumed_exchange_id", "consuming_span_id"):
        op.create_index(f"ix_tool_context_deliveries_{column}", "tool_context_deliveries", [column])


def downgrade() -> None:
    raise RuntimeError("Context delivery evidence must not be removed without a reviewed migration")
