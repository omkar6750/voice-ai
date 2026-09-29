"""Guard the missing classifier cleanup revision for fresh databases.

The historical classifier-tool rewrite was never committed. This revision
allows an empty, isolated database to initialize but deliberately refuses to
stamp a populated legacy database that still needs the rewrite. Implement the
full data migration before applying this branch to such a database.
"""

import sqlalchemy as sa
from alembic import op

revision = "0023_collapse_classifier_tools"
down_revision = "0022_tool_media_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    old_tools = bind.scalar(
        sa.text("SELECT count(*) FROM tools WHERE name IN ('classify_jev', 'classify_llm')")
    )
    old_config = bind.scalar(
        sa.text(
            "SELECT count(*) FROM agent_versions "
            "WHERE config::text LIKE '%classify_jev%' "
            "OR config::text LIKE '%classify_llm%'"
        )
    )
    if old_tools or old_config:
        raise RuntimeError(
            "Legacy classifier tools require the complete 0023 data rewrite; "
            "do not stamp this database with the fresh-database guard"
        )


def downgrade() -> None:
    pass
