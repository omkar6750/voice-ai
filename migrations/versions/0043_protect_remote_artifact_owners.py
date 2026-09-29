"""Protect Supabase-backed diagnostics as well as recordings from owner cascades."""

from alembic import op

revision = "0043_remote_artifact_guard"
down_revision = "0042_recording_storage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION guard_recording_owner_delete() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM run_artifacts
                WHERE run_id = OLD.id
                  AND storage_backend IN ('cloudinary', 'supabase')
                  AND deleted_at IS NULL
            ) THEN
                RAISE EXCEPTION 'manually delete remote artifacts before deleting run'
                    USING ERRCODE = '23514';
            END IF;
            RETURN OLD;
        END; $$;
    """)


def downgrade() -> None:
    raise RuntimeError("Remote artifact deletion protection cannot be weakened")
