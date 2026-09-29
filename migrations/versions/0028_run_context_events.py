"""Durable asynchronous result inbox for the next caller turn."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0028_run_context_events"
down_revision = "0027_align_postgres_model_parity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "run_context_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "run_id", sa.String(36), sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("tool_invocation_id", sa.String(36)),
        sa.Column("dedupe_key", sa.String(255), nullable=False),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("source_reference", sa.String(255)),
        sa.Column("connection_id", sa.String(36)),
        sa.Column("provider_message_id", sa.String(255)),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False, server_default="pending"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.Column("context_message_index", sa.Integer()),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("consumed_exchange_id", sa.String(36)),
        sa.Column("consuming_span_id", sa.String(36)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("run_id", "dedupe_key", name="uq_run_context_event_dedupe"),
        sa.CheckConstraint(
            "status IN ('pending','delivered','consumed','ended_before_delivery')",
            name="ck_run_context_event_status",
        ),
        sa.CheckConstraint(
            "source IN ('tool_result','whatsapp_receipt')",
            name="ck_run_context_event_source",
        ),
        sa.CheckConstraint(
            "context_message_index IS NULL OR context_message_index >= 0",
            name="ck_run_context_event_index",
        ),
    )
    op.create_index(
        "ix_run_context_event_pending", "run_context_events", ["run_id", "status", "occurred_at"]
    )
    op.create_index(
        "ix_run_context_events_tool_invocation_id", "run_context_events", ["tool_invocation_id"]
    )
    op.create_index(
        "ix_run_context_event_provider_message",
        "run_context_events",
        ["connection_id", "provider_message_id"],
    )


def downgrade() -> None:
    raise RuntimeError(
        "Asynchronous tool outcomes must not be deleted without a reviewed migration"
    )
