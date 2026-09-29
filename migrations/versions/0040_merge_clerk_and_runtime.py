"""Join the Clerk and runtime histories and scope delayed context events."""

from importlib import import_module

import sqlalchemy as sa
from alembic import op

revision = "0040_merge_clerk_and_runtime"
down_revision = ("0039_clerk_webhook_events", "0029_remove_unused_wait_config")
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()

    # A database already at the Clerk head saw the historical 0023 guard,
    # rather than the full classifier rewrite. Recheck the data at the join.
    legacy_count = connection.scalar(
        sa.text("SELECT count(*) FROM tools WHERE name IN ('classify_jev', 'classify_llm')")
    )
    legacy_config_count = connection.scalar(
        sa.text(
            "SELECT count(*) FROM agent_versions "
            "WHERE config::text LIKE '%classify_jev%' OR config::text LIKE '%classify_llm%'"
        )
    )
    if legacy_count or legacy_config_count:
        import_module("migrations.versions.0023_collapse_classifier_tools").upgrade()

    columns = {column["name"] for column in sa.inspect(connection).get_columns("run_context_events")}
    if "org_id" not in columns:
        op.add_column("run_context_events", sa.Column("org_id", sa.String(36), nullable=True))
    connection.execute(
        sa.text(
            "UPDATE run_context_events AS event SET org_id = run.org_id "
            "FROM runs AS run WHERE event.run_id = run.id AND event.org_id IS NULL"
        )
    )
    unscoped = connection.scalar(
        sa.text("SELECT count(*) FROM run_context_events WHERE org_id IS NULL")
    )
    mismatched = connection.scalar(
        sa.text(
            "SELECT count(*) FROM run_context_events AS event "
            "JOIN runs AS run ON run.id = event.run_id WHERE event.org_id <> run.org_id"
        )
    )
    if unscoped or mismatched:
        raise RuntimeError("Run context events must match their run organization")
    op.alter_column("run_context_events", "org_id", existing_type=sa.String(36), nullable=False)
    op.create_foreign_key(
        "fk_run_context_events_org_id", "run_context_events", "organizations", ["org_id"], ["id"]
    )
    op.create_index("ix_run_context_events_org_id", "run_context_events", ["org_id"])
    op.create_index("ix_run_context_events_run_id", "run_context_events", ["run_id"])
    op.execute(
        "CREATE TRIGGER trg_run_context_event_org BEFORE INSERT OR UPDATE "
        "ON run_context_events FOR EACH ROW EXECUTE FUNCTION "
        "enforce_same_org_reference('runs','id','run_id','fk_run_context_event_run_org')"
    )


def downgrade() -> None:
    raise RuntimeError("Merged tenant ownership and classifier cleanup are not reversible")
