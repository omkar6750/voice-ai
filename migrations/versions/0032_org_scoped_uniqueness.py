"""Make customer-facing uniqueness local to an organization."""

import sqlalchemy as sa
from alembic import op

revision = "0032_org_scoped_unique"
down_revision = "0031_require_org_id"
branch_labels = None
depends_on = None

SCOPED_UNIQUES = (
    ("agents", "agents_name_key", "uq_agents_org_name", ("org_id", "name")),
    ("tools", "tools_name_key", "uq_tools_org_name", ("org_id", "name")),
    ("contacts", "contacts_phone_number_key", "uq_contacts_org_phone", ("org_id", "phone_number")),
    ("knowledge_bases", "knowledge_bases_name_key", "uq_knowledge_bases_org_name", ("org_id", "name")),
    ("integration_connections", "integration_connections_label_key", "uq_integration_connections_org_label", ("org_id", "label")),
)


def upgrade() -> None:
    connection = op.get_bind()
    for table, _old_name, _new_name, columns in SCOPED_UNIQUES:
        columns_sql = ", ".join(f'"{column}"' for column in columns)
        duplicate = connection.execute(
            sa.text(
                f'SELECT 1 FROM "{table}" GROUP BY {columns_sql} '
                "HAVING count(*) > 1 LIMIT 1"
            )
        ).first()
        if duplicate:
            raise RuntimeError(f"Cannot scope uniqueness: duplicate key exists in {table}")
    for table, old_name, new_name, columns in SCOPED_UNIQUES:
        op.drop_constraint(old_name, table, type_="unique")
        op.create_unique_constraint(new_name, table, list(columns))


def downgrade() -> None:
    raise RuntimeError(
        "Restoring global customer uniqueness would break organizations with overlapping names"
    )
