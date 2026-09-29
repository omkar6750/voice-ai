from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .common import JSONB, Base, Identity, OrganizationOwned, Updated


class KnowledgeBase(Identity, Updated, OrganizationOwned, Base):
    __tablename__ = "knowledge_bases"
    __table_args__ = (UniqueConstraint("org_id", "name", name="uq_knowledge_bases_org_name"),)
    name: Mapped[str] = mapped_column(String(120))
    config: Mapped[dict] = mapped_column(JSONB, default=dict)


class KnowledgeSource(Identity, Updated, OrganizationOwned, Base):
    __tablename__ = "knowledge_sources"
    knowledge_base_id: Mapped[str] = mapped_column(ForeignKey("knowledge_bases.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    source_path: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    ingestion_token: Mapped[str | None] = mapped_column(String(36))
    error: Mapped[str | None] = mapped_column(Text)


class KnowledgeChunk(Identity, OrganizationOwned, Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (UniqueConstraint("source_id", "ingestion_token", "ordinal"),)
    source_id: Mapped[str] = mapped_column(ForeignKey("knowledge_sources.id", ondelete="CASCADE"))
    ordinal: Mapped[int]
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(768))
    embedding_model: Mapped[str] = mapped_column(String(120))
    ingestion_token: Mapped[str] = mapped_column(String(36))
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)


class AgentVersionKnowledge(OrganizationOwned, Base):
    __tablename__ = "agent_version_knowledge"
    agent_version_id: Mapped[str] = mapped_column(ForeignKey("agent_versions.id"), primary_key=True)
    knowledge_base_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_bases.id"), primary_key=True, index=True
    )
