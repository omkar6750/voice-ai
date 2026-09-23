"""Persist flow visits and ordered tool results with typed operation evidence."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004_flow_tool_evidence"
down_revision = "0003_integrity_run_ownership"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint("uq_span_id_run", "trace_spans", ["id", "run_id"])
    op.create_unique_constraint("uq_tool_id_run", "tool_invocations", ["id", "run_id"])
    for name, length in (
        ("provider", 60),
        ("model", 160),
        ("otel_trace_id", 32),
        ("otel_span_id", 16),
    ):
        op.add_column("trace_spans", sa.Column(name, sa.String(length)))
    for name in ("input_payload", "output_payload"):
        op.add_column("trace_spans", sa.Column(name, JSONB(none_as_null=True)))
    for name in ("ttfb_ms", "ttfa_ms", "ttfat_ms", "audio_seconds"):
        op.add_column("trace_spans", sa.Column(name, sa.Float()))
        op.create_check_constraint(
            f"ck_span_{name}", "trace_spans", f"{name} IS NULL OR {name} >= 0"
        )
    for name in ("prompt_tokens", "completion_tokens", "reasoning_tokens"):
        op.add_column("trace_spans", sa.Column(name, sa.Integer()))
        op.create_check_constraint(
            f"ck_span_{name}", "trace_spans", f"{name} IS NULL OR {name} >= 0"
        )
    op.add_column("tool_invocations", sa.Column("function_call_id", sa.String(255)))
    op.add_column("tool_invocations", sa.Column("llm_operation_id", sa.String(36)))
    op.create_foreign_key(
        "fk_tool_llm_run",
        "tool_invocations",
        "trace_spans",
        ["llm_operation_id", "run_id"],
        ["id", "run_id"],
    )
    op.create_index("ix_tool_llm_operation", "tool_invocations", ["llm_operation_id"])
    op.alter_column("tool_invocations", "result", nullable=True, server_default=None)
    # Preserve existing {} results: their historical meaning is unknown.
    op.create_table(
        "flow_node_visits",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "run_id", sa.String(36), sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("node_key", sa.String(120), nullable=False),
        sa.Column("span_id", sa.String(36), nullable=False),
        sa.Column("triggered_by_tool_id", sa.String(36)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("run_id", "sequence"),
        sa.UniqueConstraint("span_id"),
        sa.CheckConstraint("sequence > 0"),
        sa.ForeignKeyConstraint(
            ["span_id", "run_id"],
            ["trace_spans.id", "trace_spans.run_id"],
            name="fk_visit_span_run",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["triggered_by_tool_id", "run_id"],
            ["tool_invocations.id", "tool_invocations.run_id"],
            name="fk_visit_tool_run",
        ),
    )
    op.create_table(
        "tool_invocation_results",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "run_id", sa.String(36), sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("tool_invocation_id", sa.String(36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("is_final", sa.Boolean(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("consumed_exchange_id", sa.String(36)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("tool_invocation_id", "sequence"),
        sa.CheckConstraint("sequence > 0"),
        sa.CheckConstraint("(consumed_at IS NULL) = (consumed_exchange_id IS NULL)"),
        sa.ForeignKeyConstraint(
            ["tool_invocation_id", "run_id"],
            ["tool_invocations.id", "tool_invocations.run_id"],
            name="fk_result_tool_run",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["consumed_exchange_id", "run_id"],
            ["exchanges.id", "exchanges.run_id"],
            name="fk_result_consumption_run",
        ),
    )
    op.create_index(
        "uq_tool_final_result",
        "tool_invocation_results",
        ["tool_invocation_id"],
        unique=True,
        postgresql_where=sa.text("is_final"),
    )
    for table, columns in (
        ("flow_node_visits", ("run_id", "triggered_by_tool_id")),
        ("tool_invocation_results", ("run_id", "tool_invocation_id", "consumed_exchange_id")),
    ):
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])
    op.execute("""
    CREATE FUNCTION guard_ordered_tool_result() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE latest integer;
    BEGIN
      IF TG_OP = 'UPDATE' THEN
        IF (to_jsonb(NEW) - 'consumed_at' - 'consumed_exchange_id') <>
           (to_jsonb(OLD) - 'consumed_at' - 'consumed_exchange_id') THEN
          RAISE EXCEPTION 'Tool result evidence is immutable' USING ERRCODE = '23514';
        END IF;
        IF OLD.consumed_at IS NOT NULL AND (
          NEW.consumed_at IS DISTINCT FROM OLD.consumed_at OR
          NEW.consumed_exchange_id IS DISTINCT FROM OLD.consumed_exchange_id
        ) THEN RAISE EXCEPTION 'Consumption evidence is immutable' USING ERRCODE = '23514'; END IF;
        RETURN NEW;
      END IF;
      PERFORM 1 FROM tool_invocations WHERE id = NEW.tool_invocation_id FOR UPDATE;
      IF EXISTS (SELECT 1 FROM tool_invocation_results WHERE tool_invocation_id = NEW.tool_invocation_id AND is_final) THEN
        RAISE EXCEPTION 'Tool already has a final result' USING ERRCODE = '23514';
      END IF;
      SELECT COALESCE(MAX(sequence), 0) INTO latest FROM tool_invocation_results
        WHERE tool_invocation_id = NEW.tool_invocation_id;
      IF NEW.sequence <> latest + 1 THEN
        RAISE EXCEPTION 'Tool result sequence must be contiguous' USING ERRCODE = '23514';
      END IF;
      RETURN NEW;
    END $$
    """)
    op.execute(
        "CREATE TRIGGER guard_tool_result BEFORE INSERT OR UPDATE ON tool_invocation_results FOR EACH ROW EXECUTE FUNCTION guard_ordered_tool_result()"
    )


def downgrade() -> None:
    raise RuntimeError("Evidence migration must not discard captured tool results; restore backup")
