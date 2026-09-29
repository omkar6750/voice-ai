"""Align legacy evidence types, timestamp nullability, and tenant indexes."""

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0037_align_legacy_tenant_schema"
down_revision = "0036_org_provider_credentials"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("browser_sessions", "created_at", nullable=True)
    op.alter_column(
        "classifier_results",
        "result",
        type_=postgresql.JSONB(none_as_null=True),
        postgresql_using="result::jsonb",
    )
    for column in ("interrupted_operation_ids", "interrupted_tool_invocation_ids"):
        op.alter_column(
            "interruption_events",
            column,
            type_=postgresql.JSONB(),
            postgresql_using=f"{column}::jsonb",
        )
    op.drop_index("ix_inbound_webhook_messages_sender_created", if_exists=True)
    op.create_index(
        "ix_inbound_webhook_messages_connection_id",
        "inbound_webhook_messages",
        ["connection_id"],
    )
    op.drop_index("ix_workspace_settings_org_id", if_exists=True)


def downgrade() -> None:
    raise RuntimeError("Tenant schema alignment must not be reversed")
