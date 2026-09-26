"""Add telephony_connection_id and from_number to calls table.

Revision ID: 0015_twilio_telephony
Revises: 0014_inbound_msg_disconnect
Create Date: 2026-09-26
"""

import sqlalchemy as sa
from alembic import op

revision = "0015_twilio_telephony"
down_revision = "0014_inbound_msg_disconnect"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "calls",
        sa.Column(
            "telephony_connection_id",
            sa.String(36),
            sa.ForeignKey("integration_connections.id"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_calls_telephony_connection_id",
        "calls",
        ["telephony_connection_id"],
    )
    op.add_column(
        "calls",
        sa.Column("from_number", sa.String(50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("calls", "from_number")
    op.drop_index("ix_calls_telephony_connection_id", table_name="calls")
    op.drop_column("calls", "telephony_connection_id")
