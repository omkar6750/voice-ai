"""Require org_id for every tenant column, including future-proofed tables."""

import sqlalchemy as sa
from alembic import op

revision = "0034_require_all_org"
down_revision = "0033_same_org_refs"
branch_labels = None
depends_on = None


def _nullable_org_tables(connection) -> list[str]:
    return list(
        connection.execute(
            sa.text(
                "SELECT column_row.table_name "
                "FROM information_schema.columns AS column_row "
                "JOIN information_schema.tables AS table_row "
                "ON table_row.table_schema = column_row.table_schema "
                "AND table_row.table_name = column_row.table_name "
                "WHERE column_row.table_schema = current_schema() "
                "AND column_row.column_name = 'org_id' "
                "AND column_row.is_nullable = 'YES' "
                "AND table_row.table_type = 'BASE TABLE' "
                "ORDER BY column_row.table_name"
            )
        ).scalars()
    )


def upgrade() -> None:
    connection = op.get_bind()
    tables = _nullable_org_tables(connection)
    for table in tables:
        null_count = connection.execute(
            sa.text(f'SELECT count(*) FROM "{table}" WHERE org_id IS NULL')
        ).scalar_one()
        if null_count:
            raise RuntimeError(f"Cannot require org_id: {table} has {null_count} unscoped rows")
    for table in tables:
        op.alter_column(table, "org_id", existing_type=sa.String(36), nullable=False)


def downgrade() -> None:
    # Migration 0031 already required org_id on the other tenant tables; this
    # revision's only correction to that revision's table inventory is this row.
    op.alter_column(
        "classifier_results", "org_id", existing_type=sa.String(36), nullable=True
    )
