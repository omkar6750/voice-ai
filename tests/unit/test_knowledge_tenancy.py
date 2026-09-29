"""Raw knowledge SQL and rebuild publication require a resolved tenant."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session
from voice_api.db.tenant_scope import bind_organization
from voice_api.knowledge.ingestion import Chunk
from voice_api.services import knowledge_service as service
from voice_runtime.contracts.knowledge import KnowledgeConfig, RetrievalConfig


@pytest.mark.asyncio
async def test_search_rejects_missing_scope_before_provider_or_sql():
    session = SimpleNamespace(sync_session=Session(), execute=AsyncMock())
    embedder = SimpleNamespace(embed=AsyncMock())
    with pytest.raises(HTTPException) as denied:
        await service.search(session, "base", "price", RetrievalConfig(), embedder)
    assert denied.value.status_code == 403
    embedder.embed.assert_not_awaited()
    session.execute.assert_not_awaited()
    session.sync_session.close()


@pytest.mark.asyncio
async def test_search_sql_filters_base_source_and_chunk_by_bound_org():
    with Session() as sync_session:
        bind_organization(sync_session, "org-one")
        session = SimpleNamespace(sync_session=sync_session, execute=AsyncMock())
        session.execute.return_value = SimpleNamespace(mappings=lambda: [])
        result = await service.search(
            session, "base", "price", RetrievalConfig(vector_weight=0), None
        )
        assert result == []
        sql, params = session.execute.await_args.args
        assert params["org_id"] == "org-one"
        for alias in ("b", "s", "c"):
            assert f"{alias}.org_id = :org_id" in str(sql)


@pytest.mark.asyncio
async def test_build_publication_retains_source_tenant(monkeypatch):
    source = SimpleNamespace(
        ingestion_token="current", org_id="org-one", status="building", error=None
    )
    monkeypatch.setattr(service, "locked_source", AsyncMock(return_value=source))
    with Session() as sync_session:
        session = SimpleNamespace(
            sync_session=sync_session, execute=AsyncMock(), add_all=Mock()
        )
        session.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: "org-one")
        assert await service.activate_build(
            session, "source", "current", [Chunk("price", {})], [[1.0] + [0.0] * 767]
        )
        assert sync_session.info["organization_scope_id"] == "org-one"
        assert "knowledge_chunks.org_id" in str(session.execute.await_args.args[0])
        assert source.status == "ready"


@pytest.mark.asyncio
async def test_background_build_binds_org_before_each_source_read(monkeypatch):
    source = SimpleNamespace(
        id="source-one",
        org_id="org-one",
        knowledge_base_id="base-one",
        ingestion_token="current",
        content="hello world",
        title="Greeting",
        status="building",
        error=None,
    )
    base = SimpleNamespace(config=KnowledgeConfig().model_dump())

    class Transaction:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

    class FakeSession:
        def __init__(self):
            self.sync_session = Session()
            self.execute = AsyncMock(
                return_value=SimpleNamespace(scalar_one_or_none=lambda: "org-one")
            )
            self.add_all = Mock()

        def begin(self):
            return Transaction()

        async def get(self, model, _source_id):
            assert self.sync_session.info.get("organization_scope_id") == "org-one"
            if model.__name__ == "KnowledgeSource":
                return source
            if model.__name__ == "KnowledgeBase":
                return base
            raise AssertionError(f"Unexpected model: {model}")

        async def scalar(self, _statement):
            assert self.sync_session.info.get("organization_scope_id") == "org-one"
            return source

    sessions = [FakeSession(), FakeSession()]

    class SessionFactory:
        def __call__(self):
            return _SessionContext(sessions.pop(0))

    class Embedder:
        async def embed(self, _text, *, title):
            assert title == "Greeting"
            return [1.0] + [0.0] * 767

    assert await service.build_source(
        "source-one", "current", SessionFactory(), Embedder()
    )
    assert source.status == "ready"


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *_args):
        self.session.sync_session.close()
        return None


def test_legacy_knowledge_import_uses_same_scoped_implementation():
    from voice_api.knowledge import service as legacy

    assert legacy.search is service.search
    assert legacy.activate_build is service.activate_build
