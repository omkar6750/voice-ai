"""Align PostgreSQL columns and indexes with the current ORM models."""

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0027_align_postgres_model_parity"
down_revision = "0026_meta_hosted_whatsapp_media"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("browser_sessions", "created_at", nullable=True)
    op.alter_column(
        "classifier_results",
        "result",
        type_=postgresql.JSONB(none_as_null=True),
        postgresql_using="result::jsonb",
        existing_nullable=True,
    )
    for column in ("interrupted_operation_ids", "interrupted_tool_invocation_ids"):
        op.alter_column(
            "interruption_events",
            column,
            type_=postgresql.JSONB(),
            postgresql_using=f"{column}::jsonb",
            existing_nullable=False,
        )
    op.drop_index("ix_inbound_webhook_messages_sender_created", if_exists=True)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_inbound_webhook_messages_connection_id "
        "ON inbound_webhook_messages (connection_id)"
    )


def downgrade() -> None:
    raise RuntimeError("PostgreSQL model parity must not be reversed")
