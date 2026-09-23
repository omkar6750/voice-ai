"""Transactional build publication and snapshot-consistent hybrid retrieval."""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from voice_runtime.contracts.knowledge import RetrievalConfig

from voice_api.knowledge.embeddings import MODEL, Embedder, normalize
from voice_api.knowledge.ingestion import chunk_markdown
from voice_api.models import KnowledgeBase, KnowledgeChunk, KnowledgeSource
from voice_api.schemas.knowledge import SearchHit, ingestion_config


async def locked_source(session: AsyncSession, source_id: str):
    return await session.scalar(
        select(KnowledgeSource).where(KnowledgeSource.id == source_id).with_for_update()
    )


def build_is_current(source, ingestion_token: str) -> bool:
    return source is not None and source.ingestion_token == ingestion_token


async def activate_build(
    session: AsyncSession,
    source_id: str,
    ingestion_token: str,
    chunks: list,
    vectors: list[list[float]],
) -> bool:
    """Caller owns transaction; source lock serializes deletion/rebuild/publication."""
    if len(chunks) != len(vectors) or not chunks:
        raise ValueError("Build must contain an embedding for every chunk")
    vectors = [normalize(vector) for vector in vectors]
    source = await locked_source(session, source_id)
    if not build_is_current(source, ingestion_token):
        return False
    await session.execute(delete(KnowledgeChunk).where(KnowledgeChunk.source_id == source_id))
    session.add_all(
        [
            KnowledgeChunk(
                id=str(uuid4()),
                source_id=source_id,
                ordinal=ordinal,
                content=chunk.content,
                embedding=vector,
                embedding_model=MODEL,
                ingestion_token=ingestion_token,
                metadata_json=chunk.metadata,
            )
            for ordinal, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True))
        ]
    )
    source.status = "ready"
    source.error = None
    source.updated_at = datetime.now(UTC)
    return True


async def build_source(
    source_id: str,
    ingestion_token: str,
    session_factory: Callable,
    embedder: Embedder,
) -> bool:
    """No DB transaction/connection remains open during provider work.

    The persisted ingestion_token acts as a fencing token. A crash leaves a visible building
    source that can be explicitly rebuilt; existing active chunks remain searchable.
    """
    try:
        async with session_factory() as session, session.begin():
            source = await session.get(KnowledgeSource, source_id)
            if not build_is_current(source, ingestion_token):
                return False
            base = await session.get(KnowledgeBase, source.knowledge_base_id)
            config = ingestion_config(base.config)
            content, title = source.content, source.title
        if len(content) > config.extraction_max_chars:
            raise ValueError("Source exceeds configured extraction limit")
        chunks = chunk_markdown(
            content, config.chunk_size, config.chunk_overlap, markdown_aware=config.markdown_aware
        )
        vectors = [await embedder.embed(chunk.content, title=title) for chunk in chunks]
        async with session_factory() as session, session.begin():
            return await activate_build(session, source_id, ingestion_token, chunks, vectors)
    except Exception:
        # Never persist provider response bodies, URLs, credentials, or source content.
        async with session_factory() as session, session.begin():
            source = await locked_source(session, source_id)
            if build_is_current(source, ingestion_token):
                source.status = "failed"
                source.error = "Knowledge build failed; verify embedding configuration and retry."
                source.updated_at = datetime.now(UTC)
        return False


def weighted_rrf(
    vector_ids: list[str],
    keyword_ids: list[str],
    vector_weight: float = 0.5,
    keyword_weight: float = 0.5,
    k: int = 60,
) -> list[tuple[str, float]]:
    """Reference implementation of the SQL fusion rule, including stable ties."""
    scores: dict[str, float] = {}
    for ids, weight in ((vector_ids, vector_weight), (keyword_ids, keyword_weight)):
        if weight <= 0:
            continue
        for rank, chunk_id in enumerate(dict.fromkeys(ids), 1):
            scores[chunk_id] = scores.get(chunk_id, 0) + weight / (k + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


SEARCH_SQL = text("""
WITH corpus AS MATERIALIZED (
    SELECT c.id AS chunk_id, c.source_id, c.ordinal, c.content, c.embedding,
           c.metadata_json, s.title, s.source_path
    FROM knowledge_chunks c JOIN knowledge_sources s ON s.id = c.source_id
    WHERE s.knowledge_base_id = :base_id AND c.embedding_model = :model
), vectors AS (
    SELECT chunk_id, row_number() OVER (
        ORDER BY embedding <=> CAST(:embedding AS vector), chunk_id
    ) AS rank
    FROM corpus WHERE CAST(:vector_weight AS float) > 0
      AND (CAST(:min_vector AS float) IS NULL OR 1 - (embedding <=> CAST(:embedding AS vector)) >= :min_vector)
    ORDER BY embedding <=> CAST(:embedding AS vector), chunk_id LIMIT :candidates
), keywords AS (
    SELECT chunk_id, row_number() OVER (
        ORDER BY ts_rank_cd(to_tsvector('simple', content),
                           websearch_to_tsquery('simple', :query)) DESC, chunk_id
    ) AS rank
    FROM corpus
    WHERE CAST(:keyword_weight AS float) > 0 AND to_tsvector('simple', content)
          @@ websearch_to_tsquery('simple', :query)
      AND (CAST(:min_keyword AS float) IS NULL OR ts_rank_cd(to_tsvector('simple', content), websearch_to_tsquery('simple', :query)) >= :min_keyword)
    ORDER BY rank LIMIT :candidates
), scores AS (
    SELECT chunk_id, SUM(score) AS score FROM (
        SELECT chunk_id, :vector_weight / (CAST(:rrf_k AS float) + rank) AS score FROM vectors
        UNION ALL
        SELECT chunk_id, :keyword_weight / (CAST(:rrf_k AS float) + rank) AS score FROM keywords
    ) combined GROUP BY chunk_id
)
SELECT c.chunk_id, c.source_id, c.ordinal, c.content, c.metadata_json AS metadata,
       c.title, c.source_path, scores.score
FROM scores JOIN corpus c USING (chunk_id)
ORDER BY scores.score DESC, c.chunk_id LIMIT :top_k
""")


def apply_budget(hits: list[SearchHit], budget: int) -> list[SearchHit]:
    result = []
    for hit in hits:
        content = hit.content.encode("utf-8")[:budget].decode("utf-8", errors="ignore")
        if not content:
            break
        result.append(hit.model_copy(update={"content": content}))
        budget -= len(content.encode("utf-8"))
        if budget <= 0:
            break
    return result


async def search(
    session: AsyncSession,
    base_id: str,
    query: str,
    config: RetrievalConfig,
    embedder: Embedder | None,
) -> list[SearchHit]:
    if not query.strip():
        raise ValueError("Search query must not be blank")
    if config.vector_weight and embedder is None:
        raise ValueError("Vector search requires a configured embedding adapter")
    async with asyncio.timeout(config.timeout_secs):
        vector = (
            normalize(await embedder.embed(query, query=True))
            if config.vector_weight
            else [1.0] + [0.0] * 767
        )
        await session.execute(
            text("SELECT set_config('statement_timeout', :timeout, true)"),
            {"timeout": str(max(1, int(config.timeout_secs * 1000)))},
        )
        rows = await session.execute(
            SEARCH_SQL,
            {
                "base_id": base_id,
                "model": MODEL,
                "query": query,
                "embedding": "[" + ",".join(str(value) for value in vector) + "]",
                "vector_weight": config.vector_weight,
                "keyword_weight": config.keyword_weight,
                "candidates": max(50, config.top_k * 10),
                "top_k": config.top_k,
                "rrf_k": config.rrf_k,
                "min_vector": config.min_vector_similarity,
                "min_keyword": config.min_keyword_score,
            },
        )
        hits = [SearchHit.model_validate(dict(row)) for row in rows.mappings()]
        return apply_budget(hits, config.result_budget_tokens)
