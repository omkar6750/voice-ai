"""Tenant-owned text conversations, executions and finalized messages."""

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .common import JSONB, Base, Created, Identity, OrganizationOwned, Updated


class ChatConversation(Identity, Updated, OrganizationOwned, Base):
    __tablename__ = "chat_conversations"
    agent_version_id: Mapped[str] = mapped_column(ForeignKey("agent_versions.id"), index=True)
    revision: Mapped[int]
    snapshot: Mapped[dict] = mapped_column(JSONB)
    contact_id: Mapped[str | None] = mapped_column(ForeignKey("contacts.id"))
    contact_snapshot: Mapped[dict] = mapped_column(JSONB)
    scenario: Mapped[str] = mapped_column(String(100), default="manual")
    status: Mapped[str] = mapped_column(String(30), default="created")
    checkpoint: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[dict | None] = mapped_column(JSONB)
    active_run_id: Mapped[str | None] = mapped_column(ForeignKey("runs.id"))


class ChatExecution(Identity, Created, OrganizationOwned, Base):
    __tablename__ = "chat_executions"
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("chat_conversations.id", ondelete="CASCADE"), index=True
    )
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), unique=True)


class ChatMessage(Identity, Created, OrganizationOwned, Base):
    __tablename__ = "chat_messages"
    __table_args__ = (UniqueConstraint("run_id", "sequence"),)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("chat_conversations.id", ondelete="CASCADE"), index=True
    )
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"))
    sequence: Mapped[int]
    kind: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSONB)
