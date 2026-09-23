"""Index account-scoped provider receipts without unrelated index duplication."""

from alembic import op

revision = "0009_receipt_index"
down_revision = "0008_ingestion_token"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_tool_provider_receipt", "tool_invocations", ["connection_id", "provider_message_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_tool_provider_receipt", table_name="tool_invocations")
