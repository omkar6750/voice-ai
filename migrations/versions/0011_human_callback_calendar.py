"""Add Google Calendar integrations and human callback booking fields."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0011_human_callback_calendar"
down_revision = "0010_execution_ownership"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "calendar_integrations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False, server_default="google_calendar"),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("calendar_id", sa.String(120), nullable=False, server_default="primary"),
        sa.Column("timezone", sa.String(80), nullable=False, server_default="UTC"),
        sa.Column("scopes", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("token_expires_at", sa.DateTime(timezone=True)),
        sa.Column("connected_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
    )
    op.create_table(
        "calendar_integration_secrets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "calendar_integration_id",
            sa.String(36),
            sa.ForeignKey("calendar_integrations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("ciphertext", sa.Text(), nullable=False),
        sa.Column("key_id", sa.String(80), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("calendar_integration_id", "name"),
    )
    op.create_table(
        "calendar_oauth_states",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("state_hash", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "calendar_integration_id",
            sa.String(36),
            sa.ForeignKey("calendar_integrations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_calendar_oauth_states_calendar_integration_id",
        "calendar_oauth_states",
        ["calendar_integration_id"],
    )
    for name, col in (
        ("callback_mode", "automatic"),
        ("role_key", None),
        ("bookable_person_key", None),
        ("calendar_event_id", None),
        ("reason", None),
    ):
        op.add_column(
            "callbacks",
            sa.Column(
                name,
                sa.String(20)
                if name == "callback_mode"
                else sa.Text()
                if name in ("calendar_event_id", "reason")
                else sa.String(120),
                server_default=col,
            ),
        )
    for name in (
        "requested_window_start",
        "requested_window_end",
        "scheduled_start",
        "scheduled_end",
    ):
        op.add_column("callbacks", sa.Column(name, sa.DateTime(timezone=True)))
    op.add_column(
        "callbacks",
        sa.Column(
            "calendar_integration_id", sa.String(36), sa.ForeignKey("calendar_integrations.id")
        ),
    )
    op.create_index(
        "ix_callbacks_calendar_integration_id", "callbacks", ["calendar_integration_id"]
    )
    op.create_index(
        "ix_callbacks_human_scheduled",
        "callbacks",
        ["scheduled_start"],
        postgresql_where=sa.text("callback_mode = 'human' AND status = 'scheduled'"),
    )


def downgrade() -> None:
    raise RuntimeError("Human callback calendar data must not be removed")
