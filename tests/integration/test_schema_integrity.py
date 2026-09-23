"""Opt-in isolated PostgreSQL checks; test data rolls back and no providers execute."""

import asyncio
import os

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool
from voice_api.main import RevisionBody, update_agent_version
from voice_api.models import (
    Agent,
    AgentVersion,
    Call,
    ConversationMessage,
    Exchange,
)
from voice_api.models.common import new_id

pytestmark = pytest.mark.skipif(
    not os.getenv("VOICE_TEST_DATABASE_URL"), reason="Set isolated VOICE_TEST_DATABASE_URL"
)


async def test_two_connections_cannot_overwrite_same_draft():
    engine = create_async_engine(os.environ["VOICE_TEST_DATABASE_URL"], poolclass=NullPool)
    agent_id, version_id = new_id(), new_id()
    config = {
        "name": "test",
        "flow": {"initial_node": "greeting", "nodes": [{"id": "greeting", "terminal": True}]},
    }
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            session.add(Agent(id=agent_id, name=agent_id))
            await session.flush()
            session.add(
                AgentVersion(
                    id=version_id,
                    agent_id=agent_id,
                    version=1,
                    revision=1,
                    status="draft",
                    config=config,
                )
            )
            await session.commit()

        async def edit(persona):
            async with AsyncSession(engine, expire_on_commit=False) as session:
                try:
                    await update_agent_version(
                        version_id,
                        RevisionBody(revision=1, config={**config, "persona": persona}),
                        session,
                        None,
                    )
                    return 200
                except HTTPException as error:
                    return error.status_code

        assert sorted(await asyncio.gather(edit("first"), edit("second"))) == [200, 409]
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM agent_versions WHERE id = :id"), {"id": version_id}
            )
            await connection.execute(text("DELETE FROM agents WHERE id = :id"), {"id": agent_id})
        await engine.dispose()


async def new_agent(client):
    config = {
        "name": "test",
        "flow": {"initial_node": "greeting", "nodes": [{"id": "greeting", "terminal": True}]},
    }
    response = await client.post("/api/agents", json={"name": new_id(), "config": config})
    assert response.status_code == 201, response.text
    return response.json()


async def rejected_sql(database, statement, parameters):
    with pytest.raises(IntegrityError):
        async with database.begin_nested():
            await database.execute(text(statement), parameters)


async def test_publication_direct_sql_and_clone(client, database):
    agent = await new_agent(client)
    version_id = agent["version_id"]
    response = await client.post(f"/api/agent-versions/{version_id}/publish", json={"revision": 1})
    assert response.status_code == 200, response.text
    for statement in (
        "UPDATE agent_versions SET config = '{}' WHERE id = :id",
        "UPDATE agent_versions SET status = 'draft' WHERE id = :id",
        "DELETE FROM agent_versions WHERE id = :id",
    ):
        await rejected_sql(database, statement, {"id": version_id})
    clone = await client.post(f"/api/agent-versions/{version_id}/clone", json={"revision": 1})
    assert clone.status_code == 201, clone.text
    assert clone.json()["version"] == 2
    row = await database.get(AgentVersion, clone.json()["id"])
    assert row.status == "draft" and row.parent_id == version_id
    assert (await database.get(Agent, agent["agent_id"])).active_version_id is None


async def test_stale_binding_edits_and_sql_guards(client, database):
    version_id = (await new_agent(client))["version_id"]
    tool = await client.post(
        "/api/tools",
        json={"name": "test_tool", "config": {"name": "test_tool", "handler": "reviewed_handler"}},
    )
    assert tool.status_code == 201, tool.text
    tool_id = tool.json()["version_id"]
    assert (
        await client.post(f"/api/tool-versions/{tool_id}/publish", json={"revision": 1})
    ).status_code == 200
    body = {"revision": 1, "binding_key": "lookup", "tool_version_id": tool_id}
    first = await client.put(f"/api/agent-versions/{version_id}/tools", json=body)
    assert first.status_code == 200, first.text
    assert first.json()["revision"] == 2
    assert (
        await client.put(f"/api/agent-versions/{version_id}/tools", json=body)
    ).status_code == 409
    assert (
        await client.post(f"/api/agent-versions/{version_id}/publish", json={"revision": 1})
    ).status_code == 409
    published = await client.post(f"/api/agent-versions/{version_id}/publish", json={"revision": 2})
    assert published.status_code == 200, published.text
    await rejected_sql(
        database, "DELETE FROM agent_version_tools WHERE agent_version_id = :id", {"id": version_id}
    )
    await rejected_sql(
        database, "UPDATE tool_versions SET config = '{}' WHERE id = :id", {"id": tool_id}
    )


async def test_activation_rejects_foreign_or_draft_version(client, database):
    first, second = await new_agent(client), await new_agent(client)
    await rejected_sql(
        database,
        "UPDATE agents SET active_version_id = :v WHERE id = :a",
        {"v": first["version_id"], "a": first["agent_id"]},
    )
    await client.post(f"/api/agent-versions/{first['version_id']}/publish", json={"revision": 1})
    await rejected_sql(
        database,
        "UPDATE agents SET active_version_id = :v WHERE id = :a",
        {"v": first["version_id"], "a": second["agent_id"]},
    )


async def test_browser_evidence_without_call_and_cross_run_rejected(client, database):
    agent = await new_agent(client)
    await client.post(f"/api/agent-versions/{agent['version_id']}/publish", json={"revision": 1})
    body = {"agent_version_id": agent["version_id"], "channel": "browser"}
    response = await client.post("/api/runs", json=body)
    assert response.status_code == 201, response.text
    run_id = response.json()["run_id"]
    assert response.json()["call_id"] is None
    second_id = (await client.post("/api/runs", json=body)).json()["run_id"]
    exchange = Exchange(id=new_id(), run_id=run_id, sequence=1, origin="greeting")
    database.add(exchange)
    await database.flush()
    message = ConversationMessage(
        id=new_id(),
        run_id=run_id,
        exchange_id=exchange.id,
        sequence=1,
        role="assistant",
        content="Hello",
    )
    database.add(message)
    await database.flush()
    timeline = await client.get(f"/api/runs/{run_id}/timeline")
    assert timeline.status_code == 200, timeline.text
    assert timeline.json()["messages"][0]["content"] == "Hello"
    assert await database.scalar(select(Call).where(Call.run_id == run_id)) is None
    await rejected_sql(
        database,
        "UPDATE conversation_messages SET run_id = :r WHERE id = :m",
        {"r": second_id, "m": message.id},
    )


async def test_migration_jsonb_and_call_unique(database):
    assert (
        await database.execute(
            text("""
        SELECT table_name, column_name FROM information_schema.columns
        WHERE table_schema = current_schema() AND data_type = 'json'
    """)
        )
    ).all() == []
    assert (
        await database.scalar(
            text("""
        SELECT count(*) FROM pg_constraint WHERE conname = 'uq_calls_run'
    """)
        )
        == 1
    )
