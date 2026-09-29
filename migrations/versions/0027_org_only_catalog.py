"""Retire the unused nested tenant catalog and add DB-owned platform authority.

Do not rewrite 0026: it has already been applied to the isolated clone.
This migration deliberately does not assign the platform role; verified Clerk
identity and organization membership must be checked immediately before seed.
"""

import sqlalchemy as sa
from alembic import op

revision = "0027_org_only_catalog"
down_revision = "0026_tenant_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    nested_count = connection.execute(sa.text("SELECT count(*) FROM workspaces")).scalar_one()
    if nested_count:
        raise RuntimeError("Cannot retire nonempty nested workspaces without an explicit data map")

    op.drop_index("ix_workspaces_organization_id", table_name="workspaces")
    op.drop_table("workspaces")
    op.create_unique_constraint(
        "uq_organizations_owner_user_id", "organizations", ["owner_user_id"]
    )
    op.create_table(
        "platform_administrator",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "assigned_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("id = 1", name="ck_platform_administrator_singleton"),
        sa.UniqueConstraint("user_id"),
    )


def downgrade() -> None:
    raise RuntimeError("Org ownership and platform authority history must not be discarded")
