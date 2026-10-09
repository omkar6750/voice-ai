"""Backfill missing contact name components without changing confirmed components."""

from alembic import op

revision = "0050_flat_contact_names"
down_revision = "0049_referrals"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(r"""
        UPDATE contacts
        SET first_name = split_part(normalized_name, ' ', 1),
            last_name = NULLIF(substring(normalized_name FROM
                length(split_part(normalized_name, ' ', 1)) + 2), '')
        FROM (
            SELECT id, regexp_replace(trim(name), '\s+', ' ', 'g') normalized_name
            FROM contacts WHERE NULLIF(trim(first_name), '') IS NULL
        ) existing
        WHERE contacts.id = existing.id
    """)


def downgrade():
    # Data repair is deliberately retained; no schema changes to undo.
    pass
