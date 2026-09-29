"""Remove unused tool and retrieval wait settings from saved versions."""

from alembic import op

revision = "0029_remove_unused_wait_config"
down_revision = "0028_run_context_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE tool_versions SET config = config - 'wait' WHERE config ? 'wait'")
    op.execute(
        """
        UPDATE agent_versions
        SET config = jsonb_set(
            config,
            '{retrieval}',
            (config->'retrieval') - 'wait'
        )
        WHERE jsonb_typeof(config->'retrieval') = 'object'
          AND (config->'retrieval') ? 'wait'
        """
    )


def downgrade() -> None:
    raise RuntimeError("Removed wait settings are not restored by downgrade")
