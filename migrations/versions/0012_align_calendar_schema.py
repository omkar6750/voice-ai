"""Align calendar migration metadata with ORM nullability and lengths."""

import sqlalchemy as sa
from alembic import op

revision = "0012_align_calendar_schema"
down_revision = "0011_human_callback_calendar"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("calendar_integrations", "updated_at", nullable=False)
    op.alter_column("calendar_integration_secrets", "updated_at", nullable=False)
    # 0011 creates a UNIQUE constraint (and its backing index), not this
    # separately named index. Older databases may have it; fresh ones do not.
    op.execute("DROP INDEX IF EXISTS ix_calendar_oauth_states_state_hash")
    op.alter_column("callbacks", "callback_mode", nullable=False)
    op.alter_column("callbacks", "role_key", type_=sa.String(100))
    op.alter_column("callbacks", "calendar_event_id", type_=sa.String(255))
    op.drop_index("ix_callbacks_human_scheduled", table_name="callbacks")


def downgrade() -> None:
    raise RuntimeError("Calendar schema alignment must not be reversed")
