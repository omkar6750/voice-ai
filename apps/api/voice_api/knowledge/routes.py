"""Mutable knowledge base control plane. Build work happens outside request transactions."""

import asyncio

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from voice_api.auth import require_operator
from voice_api.config import get_settings
from voice_api.db import SessionFactory, get_session
from voice_api.knowledge.embeddings import GeminiEmbedder
from voice_api.knowledge.ingestion import MAX_UPLOAD_BYTES, extract_upload
from voice_api.knowledge.schemas import (
    BaseCreate,
    KnowledgeConfig,
    SearchRequest,
    SourceCreate,
    ingestion_config,
)
from voice_api.knowledge.service import build_source, search
from voice_api.models import KnowledgeBase, KnowledgeChunk, KnowledgeSource
from voice_api.models.common import new_id

router = APIRouter(prefix="/api/knowledge-bases", tags=["knowledge"])
Session = Depends(get_session)
Operator = Depends(require_operator)


class BaseUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    config: KnowledgeConfig


def embedding_key() -> str:
    key = get_settings().gemini_api_key
    if not key:
        raise HTTPException(503, "Gemini embedding is not configured")
    return key


async def build_with_client(source_id: str, ingestion_token: str, key: str) -> None:
    async with httpx.AsyncClient() as client:
        await build_source(source_id, ingestion_token, SessionFactory, GeminiEmbedder(key, client))


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
    # Fence in-flight extraction when ingestion settings change; keep working chunks.
    if row.config != body.config.model_dump(mode="json"):
        sources = (
            await session.scalars(
                select(KnowledgeSource)
                .where(KnowledgeSource.knowledge_base_id == base_id)
                .with_for_update()
            )
        ).all()
        for source in sources:
            source.ingestion_token, source.status = None, "pending"
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
    base = await base_or_404(session, base_id)
    config = ingestion_config(base.config)
    source_kind = {"paste": "text", "md": "markdown"}.get(body.kind, body.kind)
    if (
        source_kind not in config.supported_sources
        or len(body.content) > config.extraction_max_chars
    ):
        raise HTTPException(422, "Source exceeds this knowledge base's ingestion settings")
    ingestion_token = new_id()
    key = embedding_key()
    row = KnowledgeSource(
        id=new_id(),
        knowledge_base_id=base_id,
        ingestion_token=ingestion_token,
        status="building",
        **body.model_dump(),
    )
    session.add(row)
    await session.commit()
    tasks.add_task(build_with_client, row.id, ingestion_token, key)
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
    await base_or_404(session, base_id)
    async with httpx.AsyncClient() as client:
        hits = await search(
            session,
            base_id,
            body.query,
            body.retrieval,
            GeminiEmbedder(embedding_key(), client) if body.retrieval.vector_weight else None,
        )
    return {"hits": [hit.model_dump() for hit in hits]}


@router.post("/{base_id}/sources/{source_id}/rebuild", status_code=202)
async def rebuild_source(
    base_id: str,
    source_id: str,
    tasks: BackgroundTasks,
    session: AsyncSession = Session,
    _: None = Operator,
) -> dict:
    key = embedding_key()
    source = await session.get(KnowledgeSource, source_id, with_for_update=True)
    if source is None or source.knowledge_base_id != base_id:
        raise HTTPException(404, "Source not found")
    source.ingestion_token, source.status, source.error = new_id(), "building", None
    await session.commit()
    tasks.add_task(build_with_client, source.id, source.ingestion_token, key)
    return {"id": source.id, "status": source.status}


@router.post("/{base_id}/uploads", status_code=202)
async def upload_source(
    base_id: str,
    file: UploadFile,
    tasks: BackgroundTasks,
    session: AsyncSession = Session,
    _: None = Operator,
) -> dict:
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    try:
        title, kind, content = await asyncio.to_thread(extract_upload, file.filename or "", raw)
        body = SourceCreate(title=title, content=content, kind=kind)
    except ValueError:
        raise HTTPException(
            422, "Unreadable source, unsupported format or upload too large"
        ) from None
    return await create_source(base_id, body, tasks, session, _)
