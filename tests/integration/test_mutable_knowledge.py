"""Mutable corpus tests with fake vectors; no embedding provider request."""

from sqlalchemy import delete, select
from voice_api.knowledge.ingestion import Chunk
from voice_api.knowledge.service import activate_build, search
from voice_api.models import KnowledgeBase, KnowledgeChunk, KnowledgeSource
from voice_api.models.common import new_id
from voice_runtime.contracts.knowledge import KnowledgeConfig, RetrievalConfig


class Embedder:
    async def embed(self, text, *, query=False, title=""):
        return [1.0] + [0.0] * 767


async def test_rebuild_fencing_and_source_deletion(database):
    base = KnowledgeBase(id=new_id(), name=new_id(), config=KnowledgeConfig().model_dump())
    database.add(base)
    await database.flush()
    source = KnowledgeSource(
        id=new_id(),
        knowledge_base_id=base.id,
        title="Info",
        kind="txt",
        content="website design",
        ingestion_token="first",
    )
    database.add(source)
    await database.flush()
    chunks = [Chunk("website design", {})]
    vectors = [[1.0] + [0.0] * 767]
    assert await activate_build(database, source.id, "first", chunks, vectors)
    await database.flush()
    source.ingestion_token = "replacement"
    await database.flush()
    assert not await activate_build(database, source.id, "first", [Chunk("stale", {})], vectors)
    first_chunk = await database.scalar(
        select(KnowledgeChunk).where(KnowledgeChunk.source_id == source.id)
    )
    assert first_chunk.content == "website design"
    assert await activate_build(database, source.id, "replacement", [Chunk("current", {})], vectors)
    await database.flush()
    current_chunk = await database.scalar(
        select(KnowledgeChunk).where(KnowledgeChunk.source_id == source.id)
    )
    assert current_chunk.content == "current"
    await database.execute(delete(KnowledgeSource).where(KnowledgeSource.id == source.id))
    await database.flush()
    assert await database.scalar(
        select(KnowledgeChunk).where(KnowledgeChunk.source_id == source.id)
    ) is None
    assert not await activate_build(database, source.id, "replacement", chunks, vectors)


async def test_retrieval_controls_and_typed_scores(database):
    base = KnowledgeBase(id=new_id(), name=new_id(), config=KnowledgeConfig().model_dump())
    database.add(base)
    await database.flush()
    source = KnowledgeSource(
        id=new_id(),
        knowledge_base_id=base.id,
        title="Info",
        kind="txt",
        content="website design",
        ingestion_token="current",
    )
    database.add(source)
    await database.flush()
    await activate_build(
        database, source.id, "current", [Chunk("website design", {})], [[1.0] + [0.0] * 767]
    )
    await database.flush()
    hits = await search(
        database, base.id, "website", RetrievalConfig(result_budget_tokens=7, rrf_k=10), Embedder()
    )
    assert len(hits) == 1 and hits[0].score_type == "weighted_rrf"
    assert len(hits[0].content.encode()) <= 7
    assert hits[0].score > 0
    hits = await search(
        database,
        base.id,
        "website",
        RetrievalConfig(vector_weight=0, min_keyword_score=100),
        Embedder(),
    )
    assert hits == []
