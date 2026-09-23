"""Mutable knowledge base control plane. Build work happens outside request transactions."""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from voice_api.auth import require_operator
from voice_api.config import get_settings
from voice_api.db import SessionFactory, get_session
from voice_api.knowledge.embeddings import GeminiEmbedder
from voice_api.knowledge.schemas import BaseCreate, KnowledgeConfig, SearchRequest, SourceCreate
from voice_api.knowledge.service import build_source, search
from voice_api.models import KnowledgeBase, KnowledgeChunk, KnowledgeSource
from voice_api.models.common import new_id

router = APIRouter(prefix="/api/knowledge-bases", tags=["knowledge"])
Session = Depends(get_session)
Operator = Depends(require_operator)


class BaseUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    config: KnowledgeConfig


def embedder() -> GeminiEmbedder:
    key = get_settings().gemini_api_key
    if not key:
        raise HTTPException(503, "Gemini embedding is not configured")
    return GeminiEmbedder(key)


async def base_or_404(session: AsyncSession, base_id: str) -> KnowledgeBase:
    base = await session.get(KnowledgeBase, base_id)
    if base is None:
        raise HTTPException(404, "Knowledge base not found")
    return base


@router.get("")
async def list_bases(session: AsyncSession = Session, _: None = Operator) -> dict:
    rows = (await session.scalars(select(KnowledgeBase).order_by(KnowledgeBase.name))).all()
    return {
        "knowledge_bases": [{"id": row.id, "name": row.name, "config": row.config} for row in rows]
    }


@router.post("", status_code=201)
async def create_base(
    body: BaseCreate,
    session: AsyncSession = Session,
    _: None = Operator,
) -> dict:
    row = KnowledgeBase(id=new_id(), name=body.name, config=body.config.model_dump(mode="json"))
    session.add(row)
    await session.commit()
    return {"id": row.id, "name": row.name, "config": row.config}


@router.patch("/{base_id}")
async def update_base(
    base_id: str,
    body: BaseUpdate,
    session: AsyncSession = Session,
    _: None = Operator,
) -> dict:
    row = await base_or_404(session, base_id)
    row.name, row.config = body.name, body.config.model_dump(mode="json")
    await session.commit()
    return {"id": row.id, "name": row.name, "config": row.config}


@router.get("/{base_id}/sources")
async def list_sources(
    base_id: str,
    session: AsyncSession = Session,
    _: None = Operator,
) -> dict:
    await base_or_404(session, base_id)
    rows = (
        await session.scalars(
            select(KnowledgeSource)
            .where(KnowledgeSource.knowledge_base_id == base_id)
            .order_by(KnowledgeSource.created_at.desc())
        )
    ).all()
    return {
        "sources": [
            {
                "id": row.id,
                "title": row.title,
                "kind": row.kind,
                "status": row.status,
                "error": row.error,
            }
            for row in rows
        ]
    }


@router.post("/{base_id}/sources", status_code=202)
async def create_source(
    base_id: str,
    body: SourceCreate,
    tasks: BackgroundTasks,
    session: AsyncSession = Session,
    _: None = Operator,
) -> dict:
    await base_or_404(session, base_id)
    build_id = new_id()
    row = KnowledgeSource(
        id=new_id(),
        knowledge_base_id=base_id,
        build_id=build_id,
        status="building",
        **body.model_dump(),
    )
    session.add(row)
    await session.commit()
    tasks.add_task(build_source, row.id, build_id, SessionFactory, embedder())
    return {"id": row.id, "status": row.status}


@router.delete("/{base_id}/sources/{source_id}", status_code=204)
async def delete_source(
    base_id: str,
    source_id: str,
    session: AsyncSession = Session,
    _: None = Operator,
) -> None:
    source = await session.get(KnowledgeSource, source_id, with_for_update=True)
    if source is None or source.knowledge_base_id != base_id:
        raise HTTPException(404, "Knowledge source not found")
    await session.execute(delete(KnowledgeChunk).where(KnowledgeChunk.source_id == source_id))
    await session.delete(source)
    await session.commit()


@router.post("/{base_id}/search")
async def search_base(
    base_id: str,
    body: SearchRequest,
    session: AsyncSession = Session,
    _: None = Operator,
) -> dict:
    base = await base_or_404(session, base_id)
    hits = await search(
        session,
        base_id,
        body.query,
        KnowledgeConfig.model_validate(base.config),
        embedder(),
    )
    return {"hits": [hit.model_dump() for hit in hits]}
