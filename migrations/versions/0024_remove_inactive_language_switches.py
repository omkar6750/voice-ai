"""Remove the inactive caller-language switches from every agent version.

This is an explicit, one-time exception to published-version immutability. Run
snapshots remain untouched so their historical config hashes stay truthful.
"""

import sqlalchemy as sa
from alembic import op

revision = "0024_remove_language_flags"
down_revision = "0023_collapse_classifier_tools"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("ALTER TABLE agent_versions DISABLE TRIGGER guard_published"))
    bind.execute(
        sa.text(
            """
            UPDATE agent_versions
            SET config = jsonb_set(
                config,
                '{language}',
                (config->'language') - 'follow_caller_language' - 'persist_requested_language',
                false
            )
            WHERE jsonb_typeof(config->'language') = 'object'
              AND (
                config #> '{language,follow_caller_language}' IS NOT NULL
                OR config #> '{language,persist_requested_language}' IS NOT NULL
              )
            """
        )
    )
    remaining = bind.scalar(
        sa.text(
            """
            SELECT count(*) FROM agent_versions
            WHERE config #> '{language,follow_caller_language}' IS NOT NULL
               OR config #> '{language,persist_requested_language}' IS NOT NULL
            """
        )
    )
    if remaining:
        raise RuntimeError(f"Inactive language switches remain in {remaining} agent versions")
    bind.execute(sa.text("ALTER TABLE agent_versions ENABLE TRIGGER guard_published"))


def downgrade() -> None:
    raise RuntimeError("Removed inactive language switch values cannot be reconstructed")
