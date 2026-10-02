"""Stage org ownership on every customer table; preserve copied legacy rows.

Columns remain nullable until every API/runtime writer supplies the tenant and
same-org links are validated. No second-org resource access is enabled here.
"""

import sqlalchemy as sa
from alembic import op

revision = "0029_stage_org_columns"
down_revision = "0028_stable_legacy_org_and_audit"
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
    "classifier_results",
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

# Existing publication/evidence immutability guards reject even this additive
# backfill. Disable only named application triggers inside the DDL transaction;
# PostgreSQL holds table locks until commit and rollback restores trigger state.
BACKFILL_GUARDS = {
    "agent_version_knowledge": ("guard_binding",),
    "agent_version_tools": ("guard_binding",),
    "agent_versions": ("guard_published", "validate_publication"),
    "agents": ("validate_activation",),
    "calls": ("guard_call_owner",),
    "classifications": ("guard_classifications",),
    "contact_facts": ("guard_contact_facts",),
    "context_summaries": ("guard_context_summaries",),
    "conversation_messages": ("validate_owner",),
    "exchanges": ("validate_owner",),
    "runs": ("guard_run_identity",),
    "tool_invocation_results": ("guard_tool_result",),
    "tool_invocations": ("validate_owner",),
    "tool_versions": ("guard_published",),
    "trace_spans": ("validate_owner",),
}


def upgrade() -> None:
    connection = op.get_bind()
    legacy_id = connection.execute(
        sa.text("SELECT organization_id FROM legacy_data_tenant WHERE id = 1")
    ).scalar_one_or_none()
    if legacy_id is None:
        unowned_rows = sum(
            connection.execute(sa.text(f"SELECT count(*) FROM {table}")).scalar_one()
            for table in CUSTOMER_TABLES
        )
        if unowned_rows:
            raise RuntimeError(
                "Verified legacy organization mapping is required to scope existing customer data"
            )
    for table in CUSTOMER_TABLES:
        op.add_column(table, sa.Column("org_id", sa.String(36), nullable=True))
        op.create_foreign_key(
            f"fk_{table}_org_id", table, "organizations", ["org_id"], ["id"]
        )
        op.create_index(f"ix_{table}_org_id", table, ["org_id"])
        before = connection.execute(sa.text(f"SELECT count(*) FROM {table}")).scalar_one()
        for trigger in BACKFILL_GUARDS.get(table, ()):
            op.execute(sa.text(f"ALTER TABLE {table} DISABLE TRIGGER {trigger}"))
        connection.execute(
            sa.text(f"UPDATE {table} SET org_id = :org_id WHERE org_id IS NULL"),
            {"org_id": legacy_id},
        )
        for trigger in BACKFILL_GUARDS.get(table, ()):
            op.execute(sa.text(f"ALTER TABLE {table} ENABLE TRIGGER {trigger}"))
        after = connection.execute(
            sa.text(f"SELECT count(*) FROM {table} WHERE org_id = :org_id"),
            {"org_id": legacy_id},
        ).scalar_one()
        if before != after:
            raise RuntimeError(f"Backfill mismatch in {table}: {before} rows before, {after} linked")


def downgrade() -> None:
    raise RuntimeError("Tenant ownership backfill must not be discarded")
