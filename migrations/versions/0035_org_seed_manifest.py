"""Track the code-owned starter catalog applied to each organization."""

import sqlalchemy as sa
from alembic import op

revision = "0035_org_seed_manifest"
down_revision = "0034_require_all_org"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("seed_manifest_version", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    raise RuntimeError("Organization seed history must not be discarded")
