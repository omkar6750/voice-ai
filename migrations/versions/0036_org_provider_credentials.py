"""Store provider API credentials as encrypted organization-owned records."""

import sqlalchemy as sa
from alembic import op

revision = "0036_org_provider_credentials"
down_revision = "0035_org_seed_manifest"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provider_credentials",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("ciphertext", sa.Text(), nullable=False),
        sa.Column("key_id", sa.String(length=80), nullable=False),
        sa.Column("updated_by_clerk_user_id", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_id", "provider", name="uq_provider_credentials_org"),
    )
    op.create_index("ix_provider_credentials_org_id", "provider_credentials", ["org_id"])


def downgrade() -> None:
    raise RuntimeError("Credential ciphertext must not be discarded by downgrade")
