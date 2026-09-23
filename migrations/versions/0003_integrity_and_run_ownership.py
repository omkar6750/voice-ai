"""Guard publication and give all conversation evidence a Run owner.

Existing IDs, legacy call columns and unknown historical timestamps are preserved.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003_integrity_run_ownership"
down_revision = "0002_configurable_runtime"
branch_labels = None
depends_on = None

TABLES = (
    "agents",
    "agent_versions",
    "tools",
    "tool_versions",
    "workspace_settings",
    "runtime_endpoints",
    "contacts",
    "calls",
    "runs",
    "exchanges",
    "conversation_messages",
    "trace_spans",
    "tool_invocations",
    "callbacks",
    "integration_connections",
    "integration_secrets",
    "integration_media",
    "knowledge_bases",
    "knowledge_sources",
    "knowledge_chunks",
    "agent_version_tools",
    "agent_version_knowledge",
    "run_artifacts",
)


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for table in TABLES:
        for column in inspector.get_columns(table):
            name = column["name"]
            if isinstance(column["type"], sa.JSON) and not isinstance(column["type"], JSONB):
                op.alter_column(table, name, type_=JSONB(), postgresql_using=f'"{name}"::jsonb')
            if name == "created_at":
                op.alter_column(table, name, server_default=sa.text("now()"))

    op.add_column(
        "runs", sa.Column("channel", sa.String(20), nullable=False, server_default="phone")
    )
    op.add_column("runs", sa.Column("contact_id", sa.String(36), sa.ForeignKey("contacts.id")))
    op.add_column(
        "calls", sa.Column("provider", sa.String(40), nullable=False, server_default="sim7600")
    )
    op.add_column("calls", sa.Column("provider_call_id", sa.String(255)))
    op.add_column("calls", sa.Column("correlation_id", sa.String(36)))
    op.add_column(
        "calls", sa.Column("provider_metadata", JSONB(), nullable=False, server_default="{}")
    )
    op.create_unique_constraint("uq_calls_run", "calls", ["run_id"])
    op.create_unique_constraint("uq_calls_correlation", "calls", ["correlation_id"])

    # Create missing execution envelopes, not reconstructed historical provider evidence.
    op.execute("""
        INSERT INTO runs (id, status, agent_version_id, resolved_config,
                          contact_snapshot, created_at, channel, contact_id)
        SELECT c.id, c.status, c.agent_version_id,
               jsonb_build_object('legacy_import', true, 'evidence_incomplete', true),
               '{}'::jsonb, now(), 'phone', c.contact_id
        FROM calls c WHERE c.run_id IS NULL
    """)
    op.execute("UPDATE calls SET run_id = id WHERE run_id IS NULL")
    op.execute("""
        UPDATE runs r SET contact_id = c.contact_id
        FROM calls c WHERE c.run_id = r.id AND r.contact_id IS NULL
    """)
    op.add_column(
        "exchanges",
        sa.Column("run_id", sa.String(36), sa.ForeignKey("runs.id", ondelete="CASCADE")),
    )
    op.execute("UPDATE exchanges e SET run_id = c.run_id FROM calls c WHERE c.id = e.call_id")
    op.alter_column("exchanges", "run_id", nullable=False)
    op.alter_column("exchanges", "call_id", nullable=True)
    op.create_unique_constraint("uq_exchange_run_sequence", "exchanges", ["run_id", "sequence"])
    op.create_unique_constraint("uq_exchange_id_run", "exchanges", ["id", "run_id"])
    op.add_column(
        "conversation_messages",
        sa.Column("run_id", sa.String(36), sa.ForeignKey("runs.id", ondelete="CASCADE")),
    )
    op.execute("""
        UPDATE conversation_messages m SET run_id = e.run_id
        FROM exchanges e WHERE e.id = m.exchange_id
    """)
    op.alter_column("conversation_messages", "run_id", nullable=False)
    op.create_foreign_key(
        "fk_message_exchange_run",
        "conversation_messages",
        "exchanges",
        ["exchange_id", "run_id"],
        ["id", "run_id"],
        ondelete="CASCADE",
    )

    for table in ("agent_versions", "tool_versions"):
        # NOT VALID preserves unknown legacy publication dates; new writes are checked.
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT ck_{table}_status CHECK (status IN ('draft','published')) NOT VALID"
        )
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT ck_{table}_published CHECK (status != 'published' OR published_at IS NOT NULL) NOT VALID"
        )
    op.create_check_constraint(
        "ck_agent_versions_revision", "agent_versions", "version > 0 AND revision > 0"
    )
    op.create_check_constraint("ck_workspace_revision", "workspace_settings", "revision > 0")
    op.create_check_constraint("ck_run_channel", "runs", "channel IN ('phone','browser')")

    # Cover every FK access path not already covered by a leading PK/unique/index column.
    inspector = sa.inspect(op.get_bind())
    for table in TABLES:
        indexed = [i["column_names"] for i in inspector.get_indexes(table)]
        indexed += [i["column_names"] for i in inspector.get_unique_constraints(table)]
        indexed += [inspector.get_pk_constraint(table)["constrained_columns"]]
        for fk in inspector.get_foreign_keys(table):
            cols = fk["constrained_columns"]
            if not any(existing[: len(cols)] == cols for existing in indexed):
                op.create_index(f"ix_{table}_{'_'.join(cols)}", table, cols)
                indexed.append(cols)
    op.create_index("ix_runs_status_created", "runs", ["status", "created_at"])
    op.create_index(
        "ix_callbacks_due_scheduled",
        "callbacks",
        ["due_at"],
        postgresql_where=sa.text("status = 'scheduled'"),
    )

    op.execute("""
    CREATE FUNCTION guard_published_version() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF OLD.status = 'published' THEN
        RAISE EXCEPTION 'Published versions are immutable' USING ERRCODE = '23514';
      END IF;
      IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
      IF NEW.id <> OLD.id THEN
        RAISE EXCEPTION 'Version identity is immutable' USING ERRCODE = '23514';
      END IF;
      RETURN NEW;
    END $$
    """)
    for table in ("agent_versions", "tool_versions"):
        op.execute(
            f"CREATE TRIGGER guard_published BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION guard_published_version()"
        )

    op.execute("""
    CREATE FUNCTION guard_agent_binding() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE owner_status text;
    BEGIN
      IF TG_OP <> 'INSERT' THEN
        SELECT status INTO owner_status FROM agent_versions
          WHERE id = OLD.agent_version_id FOR UPDATE;
        IF owner_status = 'published' THEN
          RAISE EXCEPTION 'Published bindings are immutable' USING ERRCODE = '23514';
        END IF;
      END IF;
      IF TG_OP <> 'DELETE' THEN
        SELECT status INTO owner_status FROM agent_versions
          WHERE id = NEW.agent_version_id FOR UPDATE;
        IF owner_status = 'published' THEN
          RAISE EXCEPTION 'Published bindings are immutable' USING ERRCODE = '23514';
        END IF;
      END IF;
      IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
      RETURN NEW;
    END $$
    """)
    for table in ("agent_version_tools", "agent_version_knowledge"):
        op.execute(
            f"CREATE TRIGGER guard_binding BEFORE INSERT OR UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION guard_agent_binding()"
        )

    op.execute("""
    CREATE FUNCTION validate_agent_publication() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE bound jsonb; actual_kb jsonb;
    BEGIN
      IF NEW.status <> 'published' THEN RETURN NEW; END IF;
      IF EXISTS (
        SELECT 1 FROM agent_version_tools b JOIN tool_versions t ON t.id = b.tool_version_id
        WHERE b.agent_version_id = NEW.id AND t.status <> 'published'
      ) THEN
        RAISE EXCEPTION 'Publication requires published tools' USING ERRCODE = '23514';
      END IF;
      SELECT COALESCE(jsonb_object_agg(b.binding_key,
        jsonb_build_object('tool_id', t.tool_id, 'tool_version_id', t.id)), '{}'::jsonb)
      INTO bound FROM agent_version_tools b JOIN tool_versions t ON t.id = b.tool_version_id
      WHERE b.agent_version_id = NEW.id;
      IF bound <> COALESCE(NEW.config->'tool_bindings', '{}'::jsonb) THEN
        RAISE EXCEPTION 'Tool bindings disagree with configuration' USING ERRCODE = '23514';
      END IF;
      SELECT COALESCE(jsonb_agg(knowledge_base_id ORDER BY knowledge_base_id), '[]'::jsonb)
        INTO actual_kb FROM agent_version_knowledge WHERE agent_version_id = NEW.id;
      IF actual_kb <> COALESCE((SELECT jsonb_agg(v ORDER BY v)
        FROM jsonb_array_elements_text(COALESCE(NEW.config->'knowledge_base_ids','[]'::jsonb)) v), '[]'::jsonb) THEN
        RAISE EXCEPTION 'Knowledge bindings disagree with configuration' USING ERRCODE = '23514';
      END IF;
      RETURN NEW;
    END $$
    """)
    op.execute(
        "CREATE TRIGGER validate_publication BEFORE INSERT OR UPDATE ON agent_versions FOR EACH ROW EXECUTE FUNCTION validate_agent_publication()"
    )
    op.execute("""
    CREATE FUNCTION validate_active_version() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF NEW.active_version_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM agent_versions WHERE id = NEW.active_version_id
          AND agent_id = NEW.id AND status = 'published'
      ) THEN
        RAISE EXCEPTION 'Active version must be published and belong to agent' USING ERRCODE = '23514';
      END IF;
      RETURN NEW;
    END $$
    """)
    op.execute(
        "CREATE TRIGGER validate_activation BEFORE INSERT OR UPDATE ON agents FOR EACH ROW EXECUTE FUNCTION validate_active_version()"
    )
    op.execute("""
    CREATE FUNCTION validate_evidence_owner() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_TABLE_NAME = 'exchanges' THEN
        IF NEW.call_id IS NOT NULL AND NOT EXISTS (
          SELECT 1 FROM calls WHERE id = NEW.call_id AND run_id = NEW.run_id
        ) THEN RAISE EXCEPTION 'Exchange call belongs to another run' USING ERRCODE = '23514'; END IF;
      ELSE
        IF NEW.exchange_id IS NOT NULL AND NOT EXISTS (
          SELECT 1 FROM exchanges WHERE id = NEW.exchange_id AND run_id = NEW.run_id
        ) THEN RAISE EXCEPTION 'Exchange belongs to another run' USING ERRCODE = '23514'; END IF;
      END IF;
      IF TG_OP = 'UPDATE' AND NEW.run_id IS DISTINCT FROM OLD.run_id THEN
        RAISE EXCEPTION 'Evidence run ownership is immutable' USING ERRCODE = '23514';
      END IF;
      RETURN NEW;
    END $$
    """)
    for table in ("exchanges", "conversation_messages", "trace_spans", "tool_invocations"):
        op.execute(
            f"CREATE TRIGGER validate_owner BEFORE INSERT OR UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION validate_evidence_owner()"
        )


def downgrade() -> None:
    raise RuntimeError(
        "Ownership migration retains browser evidence; restore a backup to downgrade"
    )
