"""Name the mutable-corpus fencing token without introducing KB history."""

from alembic import op

revision = "0008_ingestion_token"
down_revision = "0007_artifact_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("knowledge_sources", "knowledge_chunks"):
        op.alter_column(table, "build_id", new_column_name="ingestion_token")


def downgrade() -> None:
    for table in ("knowledge_sources", "knowledge_chunks"):
        op.alter_column(table, "ingestion_token", new_column_name="build_id")
