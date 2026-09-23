"""Pin configuration identity and reserve endpoints without unsafe restart retries."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0005_execution_safety"
down_revision = "0004_flow_tool_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name, datatype in (
        ("claim_token", sa.String(36)),
        ("claimed_at", sa.DateTime(timezone=True)),
        ("lease_expires_at", sa.DateTime(timezone=True)),
        ("config_hash", sa.String(64)),
        ("snapshot_schema_version", sa.Integer()),
        ("final_state", JSONB()),
    ):
        op.add_column("runs", sa.Column(name, datatype))
    op.create_index(
        "uq_endpoint_active_run",
        "runs",
        ["endpoint_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('claimed','running','uncertain')"),
    )
    op.create_foreign_key(
        "fk_span_parent_run",
        "trace_spans",
        "trace_spans",
        ["parent_id", "run_id"],
        ["id", "run_id"],
    )
    op.add_column("callbacks", sa.Column("request_key", sa.String(120)))
    op.create_unique_constraint("uq_callback_request_key", "callbacks", ["request_key"])
    op.add_column("callbacks", sa.Column("claim_token", sa.String(36)))
    op.add_column(
        "callbacks",
        sa.Column("automatic_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("callbacks", sa.Column("completed_at", sa.DateTime(timezone=True)))
    op.create_check_constraint(
        "ck_callback_one_auto_attempt", "callbacks", "automatic_attempts BETWEEN 0 AND 1"
    )


def downgrade() -> None:
    raise RuntimeError("Execution identities must be preserved; restore a reviewed backup")
