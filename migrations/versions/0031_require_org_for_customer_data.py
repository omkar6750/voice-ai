"""Require an organization owner on every customer resource row.

The migration fails closed if the staged backfill left any orphan row. It does
not enable access to additional organizations; API and cross-resource scope
audits remain a separate launch gate.
"""

import sqlalchemy as sa
from alembic import op

revision = "0031_require_org_id"
down_revision = "0030_scope_workspace_settings"
branch_labels = None
depends_on = None

CUSTOMER_TABLES = (
    "agent_version_knowledge",
    "agent_version_tools",
    "agent_versions",
    "agents",
    "browser_sessions",
    "calendar_integration_secrets",
    "calendar_integrations",
    "calendar_oauth_states",
    "callbacks",
    "calls",
    "classifications",
    "classifier_context_deliveries",
    "contact_facts",
    "contacts",
    "context_summaries",
    "conversation_messages",
    "exchanges",
    "flow_node_visits",
    "inbound_webhook_messages",
    "integration_connections",
    "integration_media",
    "integration_secrets",
    "interruption_events",
    "knowledge_bases",
    "knowledge_chunks",
    "knowledge_sources",
    "run_artifacts",
    "run_diagnostics",
    "runs",
    "tool_context_deliveries",
    "tool_invocation_results",
    "tool_invocations",
    "tool_versions",
    "tools",
    "trace_spans",
    "workspace_settings",
)


def upgrade() -> None:
    connection = op.get_bind()
    for table in CUSTOMER_TABLES:
        unscoped = connection.execute(
            sa.text(f'SELECT count(*) FROM "{table}" WHERE org_id IS NULL')
        ).scalar_one()
        if unscoped:
            raise RuntimeError(f"Cannot require org_id: {table} contains {unscoped} unscoped rows")
    for table in CUSTOMER_TABLES:
        op.alter_column(
            table,
            "org_id",
            existing_type=sa.String(36),
            nullable=False,
        )


def downgrade() -> None:
    for table in reversed(CUSTOMER_TABLES):
        op.alter_column(
            table,
            "org_id",
            existing_type=sa.String(36),
            nullable=True,
        )
