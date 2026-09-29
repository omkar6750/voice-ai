"""Authenticated recording storage and manual deletion snapshots/work items."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0042_recording_storage"
down_revision = "0041_named_credentials"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = [
        sa.Column("storage_backend", sa.String(20), nullable=False, server_default="local"),
        sa.Column("storage_status", sa.String(20), nullable=False, server_default="available"),
        sa.Column("vendor_public_id", sa.Text()),
        sa.Column("vendor_asset_id", sa.Text()),
        sa.Column("vendor_version", sa.BigInteger()),
        sa.Column("vendor_format", sa.String(30)),
        sa.Column("storage_error", sa.Text()),
        sa.Column("deletion_requested_at", sa.DateTime(timezone=True)),
    ]
    for column in columns:
        op.add_column("run_artifacts", column)
    op.create_unique_constraint(
        "uq_run_artifacts_vendor_public_id", "run_artifacts", ["vendor_public_id"]
    )
    op.create_table(
        "recording_deletions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("actor_id", sa.String(255), nullable=False),
        sa.Column("confirmation_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scope", sa.String(30), nullable=False),
        sa.Column("snapshot", JSONB(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "recording_deletion_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "operation_id", sa.String(36), sa.ForeignKey("recording_deletions.id"), nullable=False
        ),
        sa.Column("artifact_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error", sa.Text()),
        sa.UniqueConstraint("operation_id", "artifact_id"),
    )
    for table in ("recording_deletions", "recording_deletion_items"):
        op.create_index(f"ix_{table}_org_id", table, ["org_id"])
    for column in ("operation_id", "artifact_id"):
        op.create_index(
            f"ix_recording_deletion_items_{column}", "recording_deletion_items", [column]
        )
        parent = "recording_deletions" if column == "operation_id" else "run_artifacts"
        op.execute(
            f"CREATE TRIGGER trg_recording_item_{column}_org BEFORE INSERT OR UPDATE ON recording_deletion_items "
            f"FOR EACH ROW EXECUTE FUNCTION enforce_same_org_reference('{parent}', 'id', '{column}', 'recording_item_{column}_org')"
        )
    # A database backstop for ordinary cascading deletes. Replica-mode cleanup must
    # still call assert_runs_recordings_deletable before disabling any FK guards.
    op.execute("""
        CREATE FUNCTION guard_recording_owner_delete() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF EXISTS (SELECT 1 FROM run_artifacts WHERE run_id=OLD.id
                       AND storage_backend IN ('cloudinary', 'supabase') AND deleted_at IS NULL) THEN
                RAISE EXCEPTION 'manually delete recordings before deleting run'
                    USING ERRCODE='23514';
            END IF;
            RETURN OLD;
        END; $$;
    """)
    op.execute(
        "CREATE TRIGGER trg_run_recording_delete BEFORE DELETE ON runs "
        "FOR EACH ROW EXECUTE FUNCTION guard_recording_owner_delete()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_run_recording_delete ON runs")
    op.execute("DROP FUNCTION guard_recording_owner_delete()")
    op.drop_table("recording_deletion_items")
    op.drop_table("recording_deletions")
    op.drop_constraint("uq_run_artifacts_vendor_public_id", "run_artifacts", type_="unique")
    for name in (
        "storage_backend",
        "storage_status",
        "vendor_public_id",
        "vendor_asset_id",
        "vendor_version",
        "vendor_format",
        "storage_error",
        "deletion_requested_at",
    ):
        op.drop_column("run_artifacts", name)
