"""Allow one singleton settings row per customer organization."""

import sqlalchemy as sa
from alembic import op

revision = "0030_scope_workspace_settings"
down_revision = "0029_stage_org_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    null_rows = connection.execute(
        sa.text("SELECT count(*) FROM workspace_settings WHERE org_id IS NULL")
    ).scalar_one()
    if null_rows:
        raise RuntimeError("workspace_settings contains unscoped rows")
    op.drop_constraint("workspace_settings_pkey", "workspace_settings", type_="primary")
    op.alter_column("workspace_settings", "org_id", nullable=False)
    op.create_primary_key(
        "pk_workspace_settings", "workspace_settings", ["id", "org_id"]
    )


def downgrade() -> None:
    raise RuntimeError("Organization-owned settings must not be made global again")
