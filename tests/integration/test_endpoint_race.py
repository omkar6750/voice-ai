"""Two real database connections compete for one endpoint, without any hardware."""

import asyncio
import os

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool
from voice_api.api.v1.endpoints.execution import claim
from voice_api.db.tenant_scope import bind_organization
from voice_api.models import (
    Agent,
    AgentVersion,
    Call,
    Contact,
    LegacyDataTenant,
    Run,
    RuntimeEndpoint,
)
from voice_api.models.common import new_id
from voice_api.schemas.execution import Claim
from voice_runtime.contracts import AgentConfig


async def test_two_workers_cannot_claim_same_endpoint():
    url = os.getenv("VOICE_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set isolated VOICE_TEST_DATABASE_URL")
    engine = create_async_engine(url, poolclass=NullPool)
    agent_id, version_id, contact_id, endpoint_id = (new_id() for _ in range(4))
    run_ids, call_ids = [new_id(), new_id()], [new_id(), new_id()]
    config = AgentConfig(
        name="test",
        flow={"initial_node": "greeting", "nodes": [{"id": "greeting", "terminal": True}]},
    ).model_dump(mode="json")
    try:
        async with AsyncSession(engine) as session:
            org_id = await session.scalar(select(LegacyDataTenant.organization_id))
            if org_id is None:
                pytest.fail("Integration database must contain the isolated legacy organization")
            bind_organization(session.sync_session, org_id)
            session.add_all(
                [
                    Agent(id=agent_id, name=agent_id),
                    Contact(id=contact_id, name="race test", phone_number=contact_id),
                    RuntimeEndpoint(
                        id=endpoint_id,
                        name=endpoint_id,
                        config={"at_port": "COM16", "audio_port": "COM17"},
                    ),
                ]
            )
            await session.flush()
            session.add(
                AgentVersion(
                    id=version_id, agent_id=agent_id, version=1, status="draft", config=config
                )
            )
            await session.flush()
            for run_id in run_ids:
                session.add(
                    Run(
                        id=run_id,
                        channel="phone",
                        status="queued",
                        agent_version_id=version_id,
                        contact_id=contact_id,
                        endpoint_id=endpoint_id,
                        resolved_config=config,
                    )
                )
            await session.flush()
            for run_id, call_id in zip(run_ids, call_ids, strict=True):
                session.add(
                    Call(
                        id=call_id,
                        run_id=run_id,
                        contact_id=contact_id,
                        agent_version_id=version_id,
                        target_snapshot="+15555550100",
                        correlation_id=new_id(),
                    )
                )
            await session.commit()

        async def compete(run_id):
            async with AsyncSession(engine, expire_on_commit=False) as session:
                bind_organization(session.sync_session, org_id)
                try:
                    await claim(run_id, Claim(token=new_id(), endpoint_id=endpoint_id), session)
                    return 200
                except HTTPException as error:
                    await session.rollback()
                    return error.status_code

        assert sorted(await asyncio.gather(*(compete(run_id) for run_id in run_ids))) == [200, 409]
    finally:
        async with engine.begin() as connection:
            for model, ids in (
                (Call, call_ids),
                (Run, run_ids),
                (AgentVersion, [version_id]),
                (Agent, [agent_id]),
                (Contact, [contact_id]),
                (RuntimeEndpoint, [endpoint_id]),
            ):
                await connection.execute(delete(model).where(model.id.in_(ids)))
        await engine.dispose()
