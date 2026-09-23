"""Persist bounded analysis evidence without replacing the original conversation."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0006_analysis_history"
down_revision = "0005_execution_safety"
branch_labels = None
depends_on = None


def common():
    return [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "run_id", sa.String(36), sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("source_message_ids", JSONB(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "classifications",
        *common(),
        sa.Column("operation_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("verdict", sa.String(40)),
        sa.Column("confidence", sa.Float()),
        sa.Column("evidence", JSONB(), nullable=False),
        sa.ForeignKeyConstraint(
            ["operation_id", "run_id"], ["trace_spans.id", "trace_spans.run_id"]
        ),
        sa.CheckConstraint("confidence IS NULL OR confidence BETWEEN 0 AND 1"),
        sa.CheckConstraint(
            "(status = 'completed' AND verdict IS NOT NULL) OR (status = 'failed' AND verdict IS NULL)"
        ),
    )
    op.create_table(
        "context_summaries",
        *common(),
        sa.Column("operation_id", sa.String(36), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["operation_id", "run_id"], ["trace_spans.id", "trace_spans.run_id"]
        ),
    )
    op.create_table(
        "contact_facts",
        *common(),
        sa.Column("contact_id", sa.String(36), sa.ForeignKey("contacts.id"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("value", JSONB(), nullable=False),
        sa.Column("supersedes_id", sa.String(36), sa.ForeignKey("contact_facts.id"), unique=True),
    )
    for table in ("classifications", "context_summaries", "contact_facts"):
        op.create_index(f"ix_{table}_run_id", table, ["run_id"])
    op.create_index("ix_contact_facts_contact_id", "contact_facts", ["contact_id"])
    op.execute("""
    CREATE FUNCTION guard_analysis_history() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE message_id text;
    BEGIN
      IF TG_OP = 'UPDATE' THEN
        RAISE EXCEPTION 'Analysis history is immutable' USING ERRCODE = '23514';
      END IF;
      IF jsonb_typeof(NEW.source_message_ids) <> 'array' OR jsonb_array_length(NEW.source_message_ids) = 0 THEN
        RAISE EXCEPTION 'Analysis requires source messages' USING ERRCODE = '23514';
      END IF;
      FOR message_id IN SELECT jsonb_array_elements_text(NEW.source_message_ids) LOOP
        IF NOT EXISTS(SELECT 1 FROM conversation_messages WHERE id = message_id AND run_id = NEW.run_id) THEN
          RAISE EXCEPTION 'Analysis source must belong to run' USING ERRCODE = '23514';
        END IF;
      END LOOP;
      IF TG_TABLE_NAME = 'contact_facts' THEN
        IF NOT EXISTS(SELECT 1 FROM runs WHERE id = NEW.run_id AND contact_id = NEW.contact_id) THEN
          RAISE EXCEPTION 'Fact contact must belong to run' USING ERRCODE = '23514';
        END IF;
        IF NEW.supersedes_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM contact_facts WHERE id = NEW.supersedes_id AND contact_id = NEW.contact_id AND name = NEW.name AND occurred_at <= NEW.occurred_at) THEN
          RAISE EXCEPTION 'Invalid fact supersession' USING ERRCODE = '23514';
        END IF;
      END IF;
      RETURN NEW;
    END $$
    """)
    for table in ("classifications", "context_summaries", "contact_facts"):
        op.execute(
            f"CREATE TRIGGER guard_{table} BEFORE INSERT OR UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION guard_analysis_history()"
        )


def downgrade() -> None:
    raise RuntimeError("Analysis evidence must be preserved; restore a reviewed backup")
