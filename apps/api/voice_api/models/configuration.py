from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .common import JSONB, Base, Created, Identity, Updated


class WorkspaceSettings(Base):
    __tablename__ = "workspace_settings"
    __table_args__ = (CheckConstraint("id = 1"),)
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    revision: Mapped[int] = mapped_column(default=1)
    config: Mapped[dict] = mapped_column(JSONB, default=dict)


class RuntimeEndpoint(Identity, Updated, Base):
    __tablename__ = "runtime_endpoints"
    name: Mapped[str] = mapped_column(String(120), unique=True)
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[dict] = mapped_column(JSONB, default=dict)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Agent(Identity, Created, Base):
    __tablename__ = "agents"
    name: Mapped[str] = mapped_column(String(120), unique=True)
    active_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_versions.id", use_alter=True, name="fk_agent_active_version")
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AgentVersion(Identity, Created, Base):
    __tablename__ = "agent_versions"
    __table_args__ = (
        UniqueConstraint("agent_id", "version"),
        CheckConstraint("version > 0 AND revision > 0"),
        CheckConstraint("status IN ('draft','published')"),
        CheckConstraint("status != 'published' OR published_at IS NOT NULL"),
    )
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), index=True)
    version: Mapped[int]
    revision: Mapped[int] = mapped_column(default=1)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    config: Mapped[dict] = mapped_column(JSONB)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("agent_versions.id"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(Text)


class Tool(Identity, Created, Base):
    __tablename__ = "tools"
    name: Mapped[str] = mapped_column(String(120), unique=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ToolVersion(Identity, Created, Base):
    __tablename__ = "tool_versions"
    __table_args__ = (
        UniqueConstraint("tool_id", "version"),
        CheckConstraint("version > 0 AND revision > 0"),
        CheckConstraint("status IN ('draft','published')"),
        CheckConstraint("status != 'published' OR published_at IS NOT NULL"),
    )
    tool_id: Mapped[str] = mapped_column(ForeignKey("tools.id"), index=True)
    version: Mapped[int]
    revision: Mapped[int] = mapped_column(default=1)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    config: Mapped[dict] = mapped_column(JSONB)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("tool_versions.id"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AgentVersionTool(Base):
    __tablename__ = "agent_version_tools"
    agent_version_id: Mapped[str] = mapped_column(ForeignKey("agent_versions.id"), primary_key=True)
    binding_key: Mapped[str] = mapped_column(String(80), primary_key=True)
    tool_version_id: Mapped[str] = mapped_column(ForeignKey("tool_versions.id"), index=True)
    config: Mapped[dict] = mapped_column(JSONB, default=dict)


class Contact(Identity, Created, Base):
    __tablename__ = "contacts"
    name: Mapped[str] = mapped_column(String(120))
    phone_number: Mapped[str] = mapped_column(String(40), unique=True)
    timezone: Mapped[str | None] = mapped_column(String(80))
    business: Mapped[str | None] = mapped_column(String(240))
    source: Mapped[str | None] = mapped_column(String(240))
    language: Mapped[str | None] = mapped_column(String(30))
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
