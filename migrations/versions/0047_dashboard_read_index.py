"""Support tenant-scoped keyset pagination without reading run snapshots."""

import sqlalchemy as sa
from alembic import op

revision = "0047_dashboard_read_index"
down_revision = "0046_text_tests"
branch_labels = None
depends_on = None


def upgrade():
    with op.get_context().autocommit_block():
        op.create_index(
            "ix_runs_org_created_id",
            "runs",
            ["org_id", sa.text("created_at DESC"), sa.text("id DESC")],
            postgresql_concurrently=True,
        )


def downgrade():
    with op.get_context().autocommit_block():
        op.drop_index("ix_runs_org_created_id", table_name="runs", postgresql_concurrently=True)
