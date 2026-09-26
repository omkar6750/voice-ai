"""Persist encrypted PKCE verifiers for Google OAuth transactions."""

import sqlalchemy as sa
from alembic import op

revision = "0013_pkce_oauth_state"
down_revision = "0012_align_calendar_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "calendar_oauth_states", sa.Column("pkce_verifier_ciphertext", sa.Text(), nullable=True)
    )
    op.add_column(
        "calendar_oauth_states", sa.Column("pkce_verifier_key_id", sa.String(80), nullable=True)
    )


def downgrade() -> None:
    raise RuntimeError("PKCE verifier history must not be removed")
