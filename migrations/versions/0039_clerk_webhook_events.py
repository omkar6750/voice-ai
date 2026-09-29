"""Add replay ledger for verified Clerk webhooks."""

import sqlalchemy as sa
from alembic import op

revision = "0039_clerk_webhook_events"
down_revision = "0038_platform_support_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "clerk_webhook_events",
        sa.Column("event_id", sa.String(length=128), primary_key=True),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("clerk_webhook_events")
