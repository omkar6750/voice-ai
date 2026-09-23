"""Add configurable runtime, evidence, integrations and mutable knowledge."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "0002_configurable_runtime"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column("agents", sa.Column("active_version_id", sa.String(36), nullable=True))
    op.add_column("agents", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "agent_versions", sa.Column("revision", sa.Integer(), nullable=False, server_default="1")
    )
    op.add_column("agent_versions", sa.Column("parent_id", sa.String(36), nullable=True))
    op.add_column(
        "agent_versions", sa.Column("published_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("agent_versions", sa.Column("note", sa.Text(), nullable=True))
    op.add_column("contacts", sa.Column("timezone", sa.String(80), nullable=True))
    op.add_column("contacts", sa.Column("business", sa.String(240), nullable=True))
    op.add_column("contacts", sa.Column("source", sa.String(240), nullable=True))
    op.add_column("contacts", sa.Column("language", sa.String(30), nullable=True))
    op.add_column(
        "contacts", sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}")
    )
    op.add_column("calls", sa.Column("run_id", sa.String(36), nullable=True))
    op.add_column("calls", sa.Column("target_snapshot", sa.String(40), nullable=True))
    op.add_column("calls", sa.Column("modem_start", sa.JSON(), nullable=False, server_default="{}"))
    op.add_column("calls", sa.Column("modem_end", sa.JSON(), nullable=False, server_default="{}"))
    op.add_column("calls", sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("calls", sa.Column("created_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        "fk_agents_active_version",
        "agents",
        "agent_versions",
        ["active_version_id"],
        ["id"],
        use_alter=True,
    )
    op.create_foreign_key(
        "fk_agent_versions_parent", "agent_versions", "agent_versions", ["parent_id"], ["id"]
    )

    op.create_table(
        "workspace_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("config", sa.JSON(), nullable=False, server_default="{}"),
        sa.CheckConstraint("id = 1"),
    )
    op.create_table(
        "tools",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False, unique=True),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "tool_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tool_id", sa.String(36), sa.ForeignKey("tools.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("parent_id", sa.String(36), sa.ForeignKey("tool_versions.id")),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tool_id", "version"),
        sa.CheckConstraint("version > 0 AND revision > 0"),
    )
    op.create_table(
        "runtime_endpoints",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False, unique=True),
        sa.Column("config", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("status", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "integration_connections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("label", sa.String(120), nullable=False, unique=True),
        sa.Column("provider", sa.String(60), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "integration_secrets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "connection_id",
            sa.String(36),
            sa.ForeignKey("integration_connections.id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("ciphertext", sa.Text(), nullable=False),
        sa.Column("key_id", sa.String(80), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("connection_id", "name"),
    )
    op.create_table(
        "integration_media",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "connection_id",
            sa.String(36),
            sa.ForeignKey("integration_connections.id"),
            nullable=False,
        ),
        sa.Column("provider_media_id", sa.String(120), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("source_path", sa.Text()),
        sa.Column("availability", sa.String(30), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("connection_id", "provider_media_id"),
    )
    op.create_table(
        "knowledge_bases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False, unique=True),
        sa.Column("config", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "knowledge_sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "knowledge_base_id", sa.String(36), sa.ForeignKey("knowledge_bases.id"), nullable=False
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_path", sa.Text()),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("build_id", sa.String(36)),
        sa.Column("error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "source_id",
            sa.String(36),
            sa.ForeignKey("knowledge_sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(768), nullable=False),
        sa.Column("embedding_model", sa.String(120), nullable=False),
        sa.Column("build_id", sa.String(36), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.UniqueConstraint("source_id", "build_id", "ordinal"),
    )
    op.create_table(
        "agent_version_tools",
        sa.Column(
            "agent_version_id", sa.String(36), sa.ForeignKey("agent_versions.id"), primary_key=True
        ),
        sa.Column("binding_key", sa.String(80), primary_key=True),
        sa.Column(
            "tool_version_id", sa.String(36), sa.ForeignKey("tool_versions.id"), nullable=False
        ),
        sa.Column("config", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.create_table(
        "agent_version_knowledge",
        sa.Column(
            "agent_version_id", sa.String(36), sa.ForeignKey("agent_versions.id"), primary_key=True
        ),
        sa.Column(
            "knowledge_base_id",
            sa.String(36),
            sa.ForeignKey("knowledge_bases.id"),
            primary_key=True,
        ),
    )
    op.create_table(
        "runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column(
            "agent_version_id", sa.String(36), sa.ForeignKey("agent_versions.id"), nullable=False
        ),
        sa.Column("endpoint_id", sa.String(36), sa.ForeignKey("runtime_endpoints.id")),
        sa.Column("resolved_config", sa.JSON(), nullable=False),
        sa.Column("contact_snapshot", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_foreign_key("fk_calls_run", "calls", "runs", ["run_id"], ["id"])
    op.create_table(
        "exchanges",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "call_id", sa.String(36), sa.ForeignKey("calls.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("origin", sa.String(20), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("call_id", "sequence"),
    )
    op.create_table(
        "conversation_messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "exchange_id",
            sa.String(36),
            sa.ForeignKey("exchanges.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_at", sa.DateTime(timezone=True)),
        sa.Column("interrupted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("playback_started_at", sa.DateTime(timezone=True)),
        sa.Column("playback_ended_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("exchange_id", "sequence"),
    )
    op.create_table(
        "trace_spans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "run_id", sa.String(36), sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("exchange_id", sa.String(36), sa.ForeignKey("exchanges.id", ondelete="SET NULL")),
        sa.Column("parent_id", sa.String(36), sa.ForeignKey("trace_spans.id", ondelete="SET NULL")),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("duration_ms", sa.Float()),
        sa.Column("attributes", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.create_table(
        "tool_invocations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "run_id", sa.String(36), sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("exchange_id", sa.String(36), sa.ForeignKey("exchanges.id", ondelete="SET NULL")),
        sa.Column("tool_version_id", sa.String(36), sa.ForeignKey("tool_versions.id")),
        sa.Column("binding_key", sa.String(80), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("arguments", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("result", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("connection_id", sa.String(36), sa.ForeignKey("integration_connections.id")),
        sa.Column("provider_message_id", sa.String(255)),
        sa.Column("receipts", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("idempotency_key", sa.String(120), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("run_id", "idempotency_key"),
    )
    op.create_table(
        "callbacks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("contact_id", sa.String(36), sa.ForeignKey("contacts.id"), nullable=False),
        sa.Column(
            "agent_version_id", sa.String(36), sa.ForeignKey("agent_versions.id"), nullable=False
        ),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone", sa.String(80), nullable=False),
        sa.Column("original_phrase", sa.Text(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True)),
        sa.Column("call_id", sa.String(36), sa.ForeignKey("calls.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "run_artifacts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "run_id", sa.String(36), sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(64)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    raise RuntimeError(
        "Downgrade is intentionally unsupported after call-evidence schema expansion"
    )
