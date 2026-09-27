"""Align diagnostic metadata with the PostgreSQL JSONB model type."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0021_diagnostic_metadata_jsonb"
down_revision = "0020_runtime_diagnostics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "run_diagnostics",
        "metadata",
        existing_type=sa.JSON(),
        type_=JSONB(),
        existing_nullable=False,
        postgresql_using="metadata::jsonb",
    )


def downgrade() -> None:
    raise RuntimeError("Diagnostic metadata type must not be downgraded")
