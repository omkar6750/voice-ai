"""Store provider-reported LLM total and cache token counts."""

import sqlalchemy as sa
from alembic import op

revision = "0025_llm_usage_counts"
down_revision = "0024_remove_language_flags"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name in (
        "total_tokens",
        "cache_read_input_tokens",
        "cache_creation_input_tokens",
    ):
        op.add_column("trace_spans", sa.Column(name, sa.Integer(), nullable=True))
        op.create_check_constraint(f"ck_span_{name}", "trace_spans", f"{name} IS NULL OR {name} >= 0")


def downgrade() -> None:
    for name in (
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
        "total_tokens",
    ):
        op.drop_constraint(f"ck_span_{name}", "trace_spans", type_="check")
        op.drop_column("trace_spans", name)
