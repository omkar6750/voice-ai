"""Transactional build publication and snapshot-consistent hybrid retrieval."""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from voice_api.knowledge.embeddings import MODEL, Embedder, normalize
from voice_api.knowledge.ingestion import Chunk, chunk_markdown
from voice_api.knowledge.schemas import KnowledgeConfig, SearchHit
from voice_api.models import KnowledgeBase, KnowledgeChunk, KnowledgeSource


async def locked_source(session: AsyncSession, source_id: str):
    return await session.scalar(
        select(KnowledgeSource).where(KnowledgeSource.id == source_id).with_for_update()
    )


def build_is_current(source, build_id: str) -> bool:
    return source is not None and source.build_id == build_id


async def activate_build(
    session: AsyncSession,
    source_id: str,
    build_id: str,
    chunks: list[Chunk],
    vectors: list[list[float]],
) -> bool:
    """Caller owns transaction; source lock serializes deletion/rebuild/publication."""
    if len(chunks) != len(vectors) or not chunks:
        raise ValueError("Build must contain an embedding for every chunk")
    vectors = [normalize(vector) for vector in vectors]
    source = await locked_source(session, source_id)
    if not build_is_current(source, build_id):
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
                build_id=build_id,
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
    build_id: str,
    session_factory: Callable,
    embedder: Embedder,
) -> bool:
    """No DB transaction/connection remains open during provider work.

    The persisted build_id acts as a fencing token. A crash leaves a visible building
    source that can be explicitly rebuilt; existing active chunks remain searchable.
    """
    try:
        async with session_factory() as session, session.begin():
            source = await session.get(KnowledgeSource, source_id)
            if not build_is_current(source, build_id):
                return False
            base = await session.get(KnowledgeBase, source.knowledge_base_id)
            config = KnowledgeConfig.model_validate(base.config)
            content, title = source.content, source.title
        chunks = chunk_markdown(content, config.chunk_size, config.chunk_overlap)
        vectors = [await embedder.embed(chunk.content, title=title) for chunk in chunks]
        async with session_factory() as session, session.begin():
            return await activate_build(session, source_id, build_id, chunks, vectors)
    except Exception:
        # Never persist provider response bodies, URLs, credentials, or source content.
        async with session_factory() as session, session.begin():
            source = await locked_source(session, source_id)
            if build_is_current(source, build_id):
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


# MATERIALIZED ensures distance sorting happens over the full filtered corpus,
# rather than an approximate HNSW/IVFFlat index. Both lists share one MVCC snapshot.
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
    FROM corpus WHERE :vector_weight > 0
    ORDER BY embedding <=> CAST(:embedding AS vector), chunk_id LIMIT :candidates
), keywords AS (
    SELECT chunk_id, row_number() OVER (
        ORDER BY ts_rank_cd(to_tsvector('simple', content),
                           websearch_to_tsquery('simple', :query)) DESC, chunk_id
    ) AS rank
    FROM corpus
    WHERE :keyword_weight > 0 AND to_tsvector('simple', content)
          @@ websearch_to_tsquery('simple', :query)
    ORDER BY rank LIMIT :candidates
), scores AS (
    SELECT chunk_id, SUM(score) AS score FROM (
        SELECT chunk_id, :vector_weight / (60.0 + rank) AS score FROM vectors
        UNION ALL
        SELECT chunk_id, :keyword_weight / (60.0 + rank) AS score FROM keywords
    ) combined GROUP BY chunk_id
)
SELECT c.chunk_id, c.source_id, c.ordinal, c.content, c.metadata_json AS metadata,
       c.title, c.source_path, scores.score
FROM scores JOIN corpus c USING (chunk_id)
ORDER BY scores.score DESC, c.chunk_id LIMIT :top_k
""")


def apply_budget(hits: list[SearchHit], budget: int) -> list[SearchHit]:
    """Conservative token bound: at most budget UTF-8 bytes of retrieved content.

    A byte is an upper bound for byte-based tokenizer tokens. Provenance is returned
    separately; callers must budget any additional prompt labels independently.
    """
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
    config: KnowledgeConfig,
    embedder: Embedder,
) -> list[SearchHit]:
    if not query.strip():
        raise ValueError("Search query must not be blank")
    async with asyncio.timeout(config.timeout_seconds):
        vector = normalize(await embedder.embed(query, query=True))
        await session.execute(
            text("SELECT set_config('statement_timeout', :timeout, true)"),
            {"timeout": str(max(1, int(config.timeout_seconds * 1000)))},
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
            },
        )
        hits = [SearchHit.model_validate(dict(row)) for row in rows.mappings()]
        return apply_budget(hits, config.context_budget)
