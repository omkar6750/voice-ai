"""Store contact names as first and last components."""

import sqlalchemy as sa
from alembic import op

revision = "0048_contact_name_parts"
down_revision = "0047_dashboard_read_index"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("contacts", sa.Column("first_name", sa.String(120), nullable=True))
    op.add_column("contacts", sa.Column("last_name", sa.String(120), nullable=True))
    op.execute(
        """
        UPDATE contacts
        SET first_name = split_part(normalized_name, ' ', 1),
            last_name = NULLIF(
                substring(normalized_name FROM length(split_part(normalized_name, ' ', 1)) + 2),
                ''
            )
        FROM (
            SELECT id, regexp_replace(trim(name), '\\s+', ' ', 'g') AS normalized_name
            FROM contacts
        ) AS existing
        WHERE contacts.id = existing.id
        """
    )


def downgrade():
    op.drop_column("contacts", "last_name")
    op.drop_column("contacts", "first_name")
