"""Add deleted_at to integration_connections and create inbound_webhook_messages table."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0014_inbound_msg_disconnect"
down_revision = "0013_pkce_oauth_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "integration_connections",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "inbound_webhook_messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("connection_id", sa.String(36), nullable=True),
        sa.Column("sender_phone", sa.String(40), nullable=False),
        sa.Column("provider_message_id", sa.String(255), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["connection_id"],
            ["integration_connections.id"],
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_inbound_webhook_messages_sender_phone",
        "inbound_webhook_messages",
        ["sender_phone"],
    )
    op.create_index(
        "ix_inbound_webhook_messages_received_at",
        "inbound_webhook_messages",
        ["received_at"],
    )
    op.create_index(
        "ix_inbound_webhook_messages_sender_created",
        "inbound_webhook_messages",
        ["sender_phone", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("inbound_webhook_messages")
    op.drop_column("integration_connections", "deleted_at")
