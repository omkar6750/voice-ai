"""Saved text-only agent tests and tenant guards."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0046_text_tests"
down_revision = "0045_runtime_tenant_guard"
branch_labels = None
depends_on = None


def common():
    return [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade():
    op.drop_constraint("ck_run_channel", "runs", type_="check")
    op.create_check_constraint(
        "ck_run_channel", "runs", "channel IN ('phone','browser','text_test')"
    )
    op.create_table(
        "chat_conversations",
        *common(),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "agent_version_id", sa.String(36), sa.ForeignKey("agent_versions.id"), nullable=False
        ),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("snapshot", JSONB, nullable=False),
        sa.Column("contact_id", sa.String(36), sa.ForeignKey("contacts.id")),
        sa.Column("contact_snapshot", JSONB, nullable=False),
        sa.Column("scenario", sa.String(100), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("checkpoint", JSONB),
        sa.Column("error", JSONB),
        sa.Column("active_run_id", sa.String(36), sa.ForeignKey("runs.id")),
    )
    op.create_table(
        "chat_executions",
        *common(),
        sa.Column(
            "conversation_id",
            sa.String(36),
            sa.ForeignKey("chat_conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("runs.id"), nullable=False, unique=True),
    )
    op.create_table(
        "chat_messages",
        *common(),
        sa.Column(
            "conversation_id",
            sa.String(36),
            sa.ForeignKey("chat_conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("sequence", sa.Integer, nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.UniqueConstraint("run_id", "sequence"),
    )
    for table, refs in {
        "chat_conversations": [
            ("agent_versions", "agent_version_id"),
            ("contacts", "contact_id"),
            ("runs", "active_run_id"),
        ],
        "chat_executions": [("chat_conversations", "conversation_id"), ("runs", "run_id")],
        "chat_messages": [("chat_conversations", "conversation_id"), ("runs", "run_id")],
    }.items():
        op.create_index(f"ix_{table}_org_id", table, ["org_id"])
        for parent, column in refs:
            op.execute(
                f"CREATE TRIGGER {table}_{column}_org BEFORE INSERT OR UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION enforce_same_org_reference('{parent}','id','{column}','{table}_{column}_fkey')"
            )
    op.create_index(
        "ix_chat_conversations_agent_version_id", "chat_conversations", ["agent_version_id"]
    )
    op.create_index("ix_chat_executions_conversation_id", "chat_executions", ["conversation_id"])
    op.create_index("ix_chat_messages_conversation_id", "chat_messages", ["conversation_id"])


def downgrade():
    for table in ("chat_messages", "chat_executions", "chat_conversations"):
        op.drop_table(table)
    op.drop_constraint("ck_run_channel", "runs", type_="check")
    op.create_check_constraint("ck_run_channel", "runs", "channel IN ('phone','browser')")
