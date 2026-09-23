"""Complete local recording metadata without changing reusable media retention."""

import sqlalchemy as sa
from alembic import op

revision = "0007_artifact_metadata"
down_revision = "0006_analysis_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name, datatype in (
        ("size_bytes", sa.BigInteger()),
        ("sample_rate", sa.Integer()),
        ("channels", sa.Integer()),
        ("sample_width", sa.Integer()),
        ("duration_seconds", sa.Float()),
        ("deletion_error", sa.Text()),
    ):
        op.add_column("run_artifacts", sa.Column(name, datatype))
    op.create_unique_constraint("uq_run_artifact_path", "run_artifacts", ["path"])
    op.create_index("ix_run_artifacts_expires_at", "run_artifacts", ["expires_at"])
    # run_id index was added in migration 0003.


def downgrade() -> None:
    raise RuntimeError("Artifact evidence must be preserved; restore a reviewed backup")
