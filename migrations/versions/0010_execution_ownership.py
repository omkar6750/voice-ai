"""Protect evidence ownership and prevent claimed configuration from drifting."""

from alembic import op

revision = "0010_execution_ownership"
down_revision = "0009_receipt_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table, name in (
        ("trace_spans", "fk_span_exchange_run"),
        ("tool_invocations", "fk_tool_exchange_run"),
    ):
        op.create_foreign_key(
            name,
            table,
            "exchanges",
            ["exchange_id", "run_id"],
            ["id", "run_id"],
            deferrable=True,
            initially="DEFERRED",
        )
    op.execute("""
    CREATE FUNCTION guard_execution_identity() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_TABLE_NAME = 'calls' THEN
        IF NEW.run_id IS NOT NULL AND NOT EXISTS (
          SELECT 1 FROM runs WHERE id = NEW.run_id AND agent_version_id = NEW.agent_version_id
          AND contact_id = NEW.contact_id AND channel = 'phone'
        ) THEN RAISE EXCEPTION 'Call ownership must match Run' USING ERRCODE = '23514'; END IF;
        RETURN NEW;
      END IF;
      IF NEW.id <> OLD.id OR NEW.agent_version_id <> OLD.agent_version_id OR
         NEW.contact_id IS DISTINCT FROM OLD.contact_id OR NEW.channel <> OLD.channel THEN
        RAISE EXCEPTION 'Execution ownership is immutable' USING ERRCODE = '23514';
      END IF;
      IF OLD.status <> 'queued' AND (
        NEW.resolved_config IS DISTINCT FROM OLD.resolved_config OR
        NEW.config_hash IS DISTINCT FROM OLD.config_hash OR
        NEW.snapshot_schema_version IS DISTINCT FROM OLD.snapshot_schema_version OR
        NEW.endpoint_id IS DISTINCT FROM OLD.endpoint_id OR
        NEW.contact_snapshot IS DISTINCT FROM OLD.contact_snapshot
      ) THEN RAISE EXCEPTION 'Claimed execution snapshot is immutable' USING ERRCODE = '23514'; END IF;
      RETURN NEW;
    END $$
    """)
    op.execute(
        "CREATE TRIGGER guard_call_owner BEFORE INSERT OR UPDATE ON calls FOR EACH ROW EXECUTE FUNCTION guard_execution_identity()"
    )
    op.execute(
        "CREATE TRIGGER guard_run_identity BEFORE UPDATE ON runs FOR EACH ROW EXECUTE FUNCTION guard_execution_identity()"
    )


def downgrade() -> None:
    raise RuntimeError("Ownership guarantees must not be removed without a reviewed migration")
