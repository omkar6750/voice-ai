"""MCP capabilities and run projections against disposable PostgreSQL."""

import json
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool
from voice_api.core.clerk_organizations import get_clerk_organization_directory
from voice_api.db.session import get_session
from voice_api.db.tenant_scope import bind_organization
from voice_api.main import app
from voice_api.mcp_server import dispatch, registry
from voice_api.models import (
    Agent,
    AgentVersion,
    ConversationMessage,
    Exchange,
    Organization,
    Run,
    TraceSpan,
    User,
)
from voice_api.models.common import new_id
from voice_api.models.mcp import McpToken
from voice_api.services import mcp_auth, run_debug


@pytest.fixture
async def database():
    url = os.getenv("VOICE_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set an isolated VOICE_TEST_DATABASE_URL")
    engine = create_async_engine(url, poolclass=NullPool)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        async with AsyncSession(
            bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        ) as session:
            yield session
        await transaction.rollback()
    await engine.dispose()


@pytest.fixture
async def identity(database, monkeypatch):
    user = User(id=new_id(), clerk_user_id="user_" + new_id())
    database.add(user)
    await database.flush()
    org = Organization(
        id=new_id(), clerk_org_id="org_" + new_id(), name="MCP test", owner_user_id=user.id
    )
    database.add(org)
    await database.commit()
    bind_organization(database.sync_session, org.id)
    role = {"value": "org:admin"}
    clerk_org_id, clerk_user_id = org.clerk_org_id, user.clerk_user_id

    async def membership(org_id, user_id):
        if role["value"] is None or org_id != clerk_org_id or user_id != clerk_user_id:
            return None
        return SimpleNamespace(role=role["value"])

    directory = SimpleNamespace(membership=membership)

    @asynccontextmanager
    async def factory():
        yield database

    async def session_override():
        yield database

    monkeypatch.setattr(mcp_auth, "SessionFactory", factory)
    monkeypatch.setattr(mcp_auth, "get_clerk_organization_directory", lambda: directory)
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_clerk_organization_directory] = lambda: directory
    try:
        yield user, org, role
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


async def test_tokens_store_hash_and_follow_live_roles(database, identity):
    user, org, role = identity
    row, raw = await mcp_auth.issue(database, user, org, "Codex", 30)
    token_id = row.id
    assert row.token_hash == sha256(raw.encode()).hexdigest()
    assert raw not in json.dumps({"hash": row.token_hash, "name": row.name})
    actor = await mcp_auth.authenticate(raw)
    assert actor.principal.org_role == "org:admin"
    role["value"] = "org:member"
    assert (await mcp_auth.authenticate(raw)).principal.org_role == "org:member"
    role["value"] = None
    with pytest.raises(HTTPException) as error:
        await mcp_auth.authenticate(raw)
    assert error.value.status_code == 403
    await database.execute(
        update(McpToken).where(McpToken.id == token_id).values(revoked_at=datetime.now(UTC))
    )
    await database.commit()
    with pytest.raises(HTTPException) as error:
        await mcp_auth.authenticate(raw)
    assert error.value.status_code == 401


@pytest.mark.parametrize(
    "field,value",
    [
        ("expires_at", datetime.now(UTC) - timedelta(seconds=1)),
        ("environment", "prod"),
    ],
)
async def test_expiry_and_environment_mismatch_rejected(database, identity, field, value):
    user, org, _ = identity
    row, raw = await mcp_auth.issue(database, user, org, "Codex", 7)
    await database.execute(update(McpToken).where(McpToken.id == row.id).values(**{field: value}))
    await database.commit()
    with pytest.raises(HTTPException) as error:
        await mcp_auth.authenticate(raw)
    assert error.value.status_code == 401


async def test_disabled_user_rejected(database, identity):
    user, org, _ = identity
    _, raw = await mcp_auth.issue(database, user, org, "Codex", 7)
    await database.execute(
        update(User).where(User.id == user.id).values(disabled_at=datetime.now(UTC))
    )
    await database.commit()
    with pytest.raises(HTTPException) as error:
        await mcp_auth.authenticate(raw)
    assert error.value.status_code == 403


async def test_member_mutation_denied_and_other_org_parameters_rejected(database, identity):
    user, org, role = identity
    _, raw = await mcp_auth.issue(database, user, org, "Codex", 30)
    role["value"] = "org:member"
    actor = await mcp_auth.authenticate(raw)
    tools = registry(app)
    create = next(
        op for op in tools.values() if op["path"] == "/api/v1/agents" and op["method"] == "POST"
    )
    config = {
        "name": "Forbidden",
        "flow": {
            "initial_node": "greeting",
            "nodes": [{"id": "greeting", "terminal": True, "respond_immediately": False}],
        },
    }
    status, _ = await dispatch(
        app, actor, create, {"body": {"name": "Forbidden", "config": config}}
    )
    assert status == 403
    creds = next(op for op in tools.values() if op["path"] == "/api/v1/orgs/{org_id}/credentials")
    with pytest.raises(HTTPException) as error:
        await dispatch(app, actor, creds, {"org_id": "org_other"})
    assert error.value.status_code == 403


async def test_token_rate_limit_is_database_backed(database, identity):
    _, org, _ = identity
    key = "test:" + org.id
    await mcp_auth.limit(database, key, 60, 2)
    await mcp_auth.limit(database, key, 60, 2)
    with pytest.raises(HTTPException) as error:
        await mcp_auth.limit(database, key, 60, 2)
    assert error.value.status_code == 429


async def test_admin_draft_revision_and_publication_through_dispatch(database, identity):
    user, org, _ = identity
    _, raw = await mcp_auth.issue(database, user, org, "Codex", 30)
    actor = await mcp_auth.authenticate(raw)
    tools = registry(app)

    def route(method, path):
        return next(op for op in tools.values() if op["method"] == method and op["path"] == path)

    config = {
        "name": "MCP agent",
        "flow": {
            "initial_node": "greeting",
            "nodes": [{"id": "greeting", "terminal": True, "respond_immediately": False}],
        },
    }
    status, created = await dispatch(
        app,
        actor,
        route("POST", "/api/v1/agents"),
        {"body": {"name": "MCP agent", "config": config}},
    )
    assert status == 201, created
    version = created["version_id"]
    update_draft = route("PATCH", "/api/v1/agent-versions/{version_id}")
    arguments = {"version_id": version, "body": {"revision": 1, "config": config}}
    assert (await dispatch(app, actor, update_draft, arguments))[0] == 200
    assert (await dispatch(app, actor, update_draft, arguments))[0] == 409
    status, published = await dispatch(
        app,
        actor,
        route("POST", "/api/v1/agent-versions/{version_id}/publish"),
        {"version_id": version, "body": {"revision": 2}},
    )
    assert status == 200, published
    assert (
        await dispatch(
            app,
            actor,
            update_draft,
            {"version_id": version, "body": {"revision": 2, "config": config}},
        )
    )[0] == 409


@pytest.fixture
async def execution(database, identity):
    agent = Agent(id=new_id(), name="Debug fixture")
    database.add(agent)
    await database.flush()
    config = {
        "name": "Debug fixture",
        "flow": {"initial_node": "greeting", "nodes": [{"id": "greeting", "terminal": True}]},
    }
    version = AgentVersion(
        id=new_id(), agent_id=agent.id, version=1, revision=1, status="draft", config=config
    )
    database.add(version)
    await database.flush()
    origin = datetime.now(UTC)
    run = Run(
        id=new_id(),
        agent_version_id=version.id,
        channel="browser",
        status="completed",
        started_at=origin,
        ended_at=origin + timedelta(seconds=5),
        resolved_config=config,
        contact_snapshot={},
        final_state={"evidence_incomplete": False},
    )
    database.add(run)
    await database.flush()
    exchange = Exchange(id=new_id(), run_id=run.id, sequence=1, origin="caller", created_at=origin)
    database.add(exchange)
    await database.flush()
    message = ConversationMessage(
        id=new_id(),
        run_id=run.id,
        exchange_id=exchange.id,
        sequence=1,
        role="user",
        content="Hello, I need help",
        source_at=origin,
    )
    database.add(message)
    operation = TraceSpan(
        id=new_id(),
        run_id=run.id,
        exchange_id=exchange.id,
        name="inference",
        category="llm",
        started_at=origin,
        ended_at=origin + timedelta(seconds=2),
        status="completed",
        duration_ms=2000,
        input_payload={
            "messages": [{"role": "user", "content": message.content}],
            "system_instruction": "PRIVATE_CONTEXT",
            "api_key": "secret",
        },
        output_payload={"text": "How can I help?"},
        output_state="recorded",
        attributes={},
    )
    database.add(operation)
    await database.flush()
    request = TraceSpan(
        id=new_id(),
        run_id=run.id,
        exchange_id=exchange.id,
        parent_id=operation.id,
        name="API request",
        category="http_request",
        status="completed",
        started_at=origin,
        ended_at=origin + timedelta(seconds=1),
        duration_ms=1000,
        attributes={"method": "POST", "endpoint": "/chat/completions", "http_status": 200},
    )
    database.add(request)
    await database.commit()
    return run.id, operation.id, request.id, message.id


async def test_overview_complete_without_context_or_duplicate_transcript(database, execution):
    run_id, operation_id, request_id, message_id = execution
    overview = await run_debug.inspect(database, run_id)
    encoded = json.dumps(overview)
    assert encoded.count("Hello, I need help") == 1
    assert "PRIVATE_CONTEXT" not in encoded and "secret" not in encoded
    assert overview["transcript"][0]["id"] == message_id
    assert overview["operations"][0]["id"] == operation_id
    assert overview["api_attempts"][0]["id"] == request_id
    assert overview["api_attempts"][0]["parent_id"] == operation_id
    assert overview["coverage"]["overview_complete"] is True
    full = await run_debug.details(database, run_id, [operation_id], ["context"])
    assert message_id in json.dumps(full) and encoded.count(message_id) >= 1
    assert "Hello, I need help" not in json.dumps(full)
    materialized = await run_debug.details(database, run_id, [operation_id], ["context"], True)
    assert "Hello, I need help" in json.dumps(materialized)
    default = await run_debug.details(database, run_id, [operation_id], ["input", "output"])
    assert "PRIVATE_CONTEXT" not in json.dumps(default)
    assert "secret" not in json.dumps(default)


async def test_wrong_run_operation_is_not_readable(database, execution):
    run_id, _, _, _ = execution
    with pytest.raises(HTTPException) as error:
        await run_debug.details(database, run_id, [new_id()], ["context"])
    assert error.value.status_code == 404


async def test_foreign_organization_cannot_read_run_or_logs(database, identity, execution):
    from voice_api.models.artifacts import RunArtifact
    from voice_api.services import run_debug_logs

    run_id = execution[0]
    artifact = RunArtifact(
        id=new_id(),
        run_id=run_id,
        kind="runtime_log",
        path=new_id(),
        size_bytes=0,
        sha256=sha256(b"").hexdigest(),
    )
    database.add(artifact)
    other_user = User(id=new_id(), clerk_user_id="user_" + new_id())
    database.add(other_user)
    await database.flush()
    other = Organization(
        id=new_id(),
        clerk_org_id="org_" + new_id(),
        name="Other organization",
        owner_user_id=other_user.id,
    )
    database.add(other)
    await database.commit()
    async with AsyncSession(
        bind=database.bind, join_transaction_mode="create_savepoint"
    ) as foreign:
        bind_organization(foreign.sync_session, other.id)
        for operation in (
            run_debug.inspect(foreign, run_id),
            run_debug_logs.excerpt(foreign, run_id, artifact.id, "all", None, 0, 100),
        ):
            with pytest.raises(HTTPException) as error:
                await operation
            assert error.value.status_code == 404


async def test_mcp_migration_matches_models(database):
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from voice_api.models.common import Base

    tables = {"mcp_tokens", "mcp_rate_buckets", "mcp_audit"}

    def compare(connection):
        context = MigrationContext.configure(
            connection,
            opts={
                "include_object": lambda obj, name, kind, reflected, compared: (
                    kind != "table" or name in tables
                ),
            },
        )
        return compare_metadata(context, Base.metadata)

    assert await database.bind.run_sync(compare) == []


async def test_dashboard_token_management_obeys_ownership(database, identity):
    import httpx
    from voice_api.core.clerk_auth import ClerkPrincipal
    from voice_api.mcp_server import InternalDispatch

    user, org, role = identity
    principal = ClerkPrincipal(user_id=user.clerk_user_id, org_id=org.clerk_org_id)
    base = f"/api/v1/orgs/{org.clerk_org_id}/mcp-tokens"
    other_user = User(id=new_id(), clerk_user_id="user_" + new_id())
    database.add(other_user)
    await database.commit()
    other, _ = await mcp_auth.issue(database, other_user, org, "Other member", 30)
    other_id = other.id
    role["value"] = "org:member"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=InternalDispatch(app, principal)),
        base_url="http://mcp.internal",
    ) as client:
        created = await client.post(base, json={"name": "My Codex", "days": 7})
        assert created.status_code == 201, created.text
        assert created.headers["cache-control"] == "no-store"
        body = created.json()
        mine = body["metadata"]["id"]
        listed = await client.get(base)
        assert [row["id"] for row in listed.json()] == [mine]
        assert body["token"] not in listed.text and "token_hash" not in listed.text
        assert (await client.delete(f"{base}/{other_id}")).status_code == 404
        role["value"] = "org:admin"
        assert (await client.delete(f"{base}/{other_id}")).status_code == 204
        assert (await client.delete(f"{base}/{mine}")).status_code == 204
    with pytest.raises(HTTPException) as error:
        await mcp_auth.authenticate(body["token"])
    assert error.value.status_code == 401
