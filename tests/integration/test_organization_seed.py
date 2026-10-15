"""Exercise publication guards and tenant-owned demo evidence in real PostgreSQL."""

import os
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool
from voice_api.api.v1.endpoints.agents import activate_agent, publish_agent
from voice_api.api.v1.endpoints.runs import get_run, list_runs, timeline
from voice_api.core import config as settings_module
from voice_api.db.tenant_scope import bind_organization
from voice_api.models import (
    Agent,
    AgentVersion,
    Call,
    Contact,
    ConversationMessage,
    Exchange,
    FlowNodeVisit,
    IntegrationConnection,
    Organization,
    ProviderCredential,
    Run,
    RunArtifact,
    Tool,
    TraceSpan,
    User,
    WorkspaceSettings,
)
from voice_api.models.common import new_id
from voice_api.schemas.agent import ActivateAgentBody, ExpectedRevision
from voice_api.schemas.timeline import TimelineResponse
from voice_api.services.organization_seed import SEED_MANIFEST_VERSION, seed_organization
from voice_api.services.resolution_service import fingerprint


@pytest.fixture
async def database():
    # New-org provisioning must also work in an empty migrated database, with no
    # legacy tenant to satisfy the general evidence-test fixture.
    url = os.getenv("VOICE_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set isolated VOICE_TEST_DATABASE_URL")
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            outer = await connection.begin()
            async with AsyncSession(bind=connection) as session:
                try:
                    yield session
                finally:
                    await outer.rollback()
    finally:
        await engine.dispose()


@asynccontextmanager
async def organization_session(database, *, manifest=0):
    # Separate request sessions cannot change tenant context. Share only the test
    # connection so every organization and seed is rolled back after the test.
    async with AsyncSession(
        bind=await database.connection(),
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    ) as session:
        user = User(id=new_id(), clerk_user_id="user_demo_" + new_id())
        session.add(user)
        await session.flush()
        organization = Organization(
            id=new_id(),
            clerk_org_id="org_demo_" + new_id(),
            owner_user_id=user.id,
            name="Demo seed test",
            seed_manifest_version=manifest,
        )
        session.add(organization)
        await session.flush()
        bind_organization(session.sync_session, organization.id)
        yield session, organization


@pytest.mark.asyncio
async def test_seed_is_idempotent_and_readable_without_production_credentials(
    database, monkeypatch
):
    monkeypatch.setattr(settings_module, "get_settings", lambda: SimpleNamespace(env="prod"))
    async with organization_session(database) as (session, org):
        await seed_organization(session, org.id)
        await seed_organization(session, org.id)
        assert org.seed_manifest_version == SEED_MANIFEST_VERSION
        assert await session.scalar(select(func.count()).select_from(Agent)) == 1
        assert await session.scalar(select(func.count()).select_from(AgentVersion)) == 1
        assert await session.scalar(select(func.count()).select_from(Run)) == 1
        for model in (ProviderCredential, Contact, Call, RunArtifact, IntegrationConnection, Tool):
            assert await session.scalar(select(func.count()).select_from(model)) == 0
        run = await session.scalar(select(Run))
        version = await session.get(AgentVersion, run.agent_version_id)
        agent = await session.get(Agent, version.agent_id)
        assert version.version == 1 and version.status == "draft"
        assert version.published_at is None
        assert agent.active_version_id is None
        assert run.status == "completed" and run.endpoint_id is None
        assert run.claim_token is None and run.contact_id is None
        assert run.config_hash == fingerprint(run.resolved_config)
        assert run.resolved_config["_resolved"]["agent_version_id"] == version.id
        assert run.resolved_config["_resolved"]["credentials"] == {}
        assert (await list_runs(session=session, _=None))["runs"][0]["id"] == run.id
        detail = await get_run(run.id, session=session, _=None)
        assert detail["resolved_config"]["_demo"]["source_agent_version"] == 13
        evidence = TimelineResponse.model_validate(await timeline(run.id, session=session, _=None))
        assert evidence.run.agent_id == agent.id
        assert len(evidence.messages) == 22
        assert len(evidence.exchanges) == 12
        assert len(evidence.spans) == 66
        assert all(s.input is None and s.output is None for s in evidence.spans)


@pytest.mark.asyncio
async def test_starter_requires_credentials_to_publish_and_cannot_activate_as_a_draft(
    database, monkeypatch
):
    monkeypatch.setattr(settings_module, "get_settings", lambda: SimpleNamespace(env="prod"))
    async with organization_session(database) as (session, org):
        await seed_organization(session, org.id)
        version = await session.scalar(select(AgentVersion))
        with pytest.raises(HTTPException) as rejected:
            await publish_agent(version.id, ExpectedRevision(revision=1), session=session, _=None)
        assert rejected.value.status_code == 422
        assert "credential" in str(rejected.value.detail).lower()
        assert version.status == "draft" and version.published_at is None
        with pytest.raises(HTTPException) as rejected:
            await activate_agent(
                version.agent_id, ActivateAgentBody(version_id=version.id), session=session, _=None
            )
        assert rejected.value.status_code == 422
        assert (await session.get(Agent, version.agent_id)).active_version_id is None

        credential = ProviderCredential(
            id=new_id(),
            org_id=org.id,
            provider="sarvam",
            name="Publication fixture",
            status="stored",
            version=1,
            ciphertext="unused-test-ciphertext",
            key_id="test-only",
            updated_by_clerk_user_id="user_publication_test",
        )
        session.add(credential)
        await session.flush()
        version.config = {
            **version.config,
            "credential_refs": {stage: credential.id for stage in ("llm", "stt", "tts")},
        }
        version.revision += 1
        await session.flush()
        result = await publish_agent(
            version.id, ExpectedRevision(revision=version.revision), session=session, _=None
        )
        assert result["status"] == "published"
        assert (await session.get(Agent, version.agent_id)).active_version_id is None
        # Draft edits and publication must not rewrite the recorded demo snapshot.
        run = await session.scalar(select(Run))
        assert run.resolved_config["credential_refs"] == {}
        assert run.config_hash == fingerprint(run.resolved_config)


@pytest.mark.asyncio
async def test_each_org_gets_independent_ids_and_no_foreign_tenant_references(database):
    async with organization_session(database) as (first, org):
        await seed_organization(first, org.id)
        first_run = await first.scalar(select(Run))
        identities = {}
        for model in (
            Run,
            Agent,
            AgentVersion,
            Exchange,
            ConversationMessage,
            TraceSpan,
            FlowNodeVisit,
        ):
            identities[model] = set((await first.scalars(select(model.id))).all())
        await first.commit()
    async with organization_session(database) as (second, org):
        await seed_organization(second, org.id)
        for model, original_ids in identities.items():
            copied_ids = set((await second.scalars(select(model.id))).all())
            assert copied_ids and copied_ids.isdisjoint(original_ids)
        assert await second.get(Run, first_run.id) is None
        second_run = await second.scalar(select(Run))
        visits = (await second.scalars(select(FlowNodeVisit))).all()
        assert all(v.run_id == second_run.id for v in visits)
        for visit in visits:
            assert (await second.get(TraceSpan, visit.span_id)).run_id == second_run.id


@pytest.mark.asyncio
async def test_existing_seed_and_settings_are_preserved(database):
    async with organization_session(database, manifest=1) as (session, org):
        session.add(
            WorkspaceSettings(
                id=1, org_id=org.id, revision=7, config={"recording_retention_days": 9}
            )
        )
        await session.flush()
        await seed_organization(session, org.id)
        assert org.seed_manifest_version == 1
        assert await session.scalar(select(func.count()).select_from(Agent)) == 0
        assert (await session.get(WorkspaceSettings, (1, org.id))).revision == 7
