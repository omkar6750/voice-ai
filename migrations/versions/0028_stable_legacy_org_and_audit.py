"""Keep legacy data ownership stable across owner transfers and audit transfers."""

import sqlalchemy as sa
from alembic import op

revision = "0028_stable_legacy_org_and_audit"
down_revision = "0027_org_only_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    legacy_ids = connection.execute(
        sa.text(
            "SELECT o.id FROM organizations o "
            "JOIN platform_administrator p ON p.user_id = o.owner_user_id "
            "WHERE p.id = 1"
        )
    ).scalars().all()
    if len(legacy_ids) > 1:
        raise RuntimeError("Expected at most one verified legacy organization")
    if not legacy_ids:
        # A fresh installation has no verified Clerk identity or organization
        # yet. Leave the legacy mapping empty; onboarding may create ordinary
        # organizations later, but must not invent a platform administrator.
        identity_count = connection.scalar(
            sa.text("SELECT (SELECT count(*) FROM users) + (SELECT count(*) FROM organizations)")
        )
        administrator_count = connection.scalar(
            sa.text("SELECT count(*) FROM platform_administrator")
        )
        if identity_count or administrator_count:
            raise RuntimeError(
                "Could not identify exactly one verified legacy organization for existing data"
            )
    op.create_table(
        "legacy_data_tenant",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False, unique=True),
        sa.CheckConstraint("id = 1", name="ck_legacy_data_tenant_singleton"),
    )
    if legacy_ids:
        connection.execute(
            sa.text("INSERT INTO legacy_data_tenant (id, organization_id) VALUES (1, :org_id)"),
            {"org_id": legacy_ids[0]},
        )
    op.create_table(
        "organization_audit",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("target_user_id", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_organization_audit_organization_id", "organization_audit", ["organization_id"])


def downgrade() -> None:
    raise RuntimeError("Legacy organization mapping and ownership audit cannot be discarded")
