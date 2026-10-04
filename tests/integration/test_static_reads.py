"""Bounded read projections against PostgreSQL, with all fixtures rolled back."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event, select
from voice_api.api.v1.endpoints.auth import app_context
from voice_api.core.clerk_auth import ClerkPrincipal
from voice_api.models import LegacyDataTenant, Run
from voice_api.models.common import new_id


@pytest.fixture
async def static_agent(client):
    response = await client.post(
        "/api/v1/agents",
        json={
            "name": new_id(),
            "config": {
                "name": "static read test",
                "flow": {"initial_node": "hello", "nodes": [{"id": "hello", "terminal": True}]},
            },
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_runs_keyset_ties_filters_no_snapshot_payload(client, database, static_agent):
    now = datetime.now(UTC)
    rows = [
        Run(
            id=new_id(),
            agent_version_id=static_agent["version_id"],
            status="failed",
            channel="browser",
            created_at=now,
            resolved_config={
                "system_prompt": "large" * 10000,
                "call_limits": {"max_duration_seconds": 600},
            },
            contact_snapshot={"name": "Read pagination person"},
        )
        for _ in range(61)
    ]
    database.add_all(rows)
    await database.flush()
    ids = []
    cursor = None
    while True:
        parameters = {"limit": 25, "agent_version_id": static_agent["version_id"]}
        if cursor:
            parameters["cursor"] = cursor
        response = await client.get("/api/v1/runs", params=parameters)
        assert response.status_code == 200, response.text
        page = response.json()
        assert len(page["runs"]) <= 25
        assert all("resolved_config" not in run for run in page["runs"])
        assert all(run["transport_provider"] == "dashboard" for run in page["runs"])
        ids.extend(run["id"] for run in page["runs"])
        cursor = page["next_cursor"]
        if not page["has_more"]:
            break
    assert ids == sorted((row.id for row in rows), reverse=True)
    first = (await client.get("/api/v1/runs", params={"limit": 1, "status": "failed"})).json()
    assert (
        await client.get(
            "/api/v1/runs", params={"cursor": first["next_cursor"], "status": "completed"}
        )
    ).status_code == 422
    assert (await client.get("/api/v1/runs", params={"limit": 101})).status_code == 422
    empty = await client.get(
        "/api/v1/runs", params={"created_after": (now + timedelta(days=1)).isoformat()}
    )
    assert empty.json()["runs"] == []
    assert (
        len(
            (
                await client.get("/api/v1/runs", params={"search": "pagination", "limit": 100})
            ).json()["runs"]
        )
        == 61
    )


async def test_agent_catalog_is_one_query_and_version_summary_omits_config(
    client, database, static_agent
):
    statements = []
    connection = await database.connection()

    def collect(_conn, _cursor, statement, *_args):
        statements.append(statement)

    event.listen(connection.sync_connection, "before_cursor_execute", collect)
    try:
        result = await client.get("/api/v1/agents")
    finally:
        event.remove(connection.sync_connection, "before_cursor_execute", collect)
    assert result.status_code == 200
    assert len(statements) == 1
    found = next(
        agent for agent in result.json()["agents"] if agent["id"] == static_agent["agent_id"]
    )
    assert found["latest_version_id"] == static_agent["version_id"]
    summary = await client.get(f"/api/v1/agents/{static_agent['agent_id']}/versions?view=summary")
    assert summary.status_code == 200
    assert "config" not in summary.json()["versions"][0]
    detail = await client.get(f"/api/v1/agent-versions/{static_agent['version_id']}")
    assert detail.status_code == 200
    assert detail.json()["config"]["name"] == "static read test"


async def test_projected_context_preserves_registered_owner_state(database):
    from voice_api.models import Organization, PlatformAdministrator, User

    org_id = await database.scalar(select(LegacyDataTenant.organization_id))
    org = await database.get(Organization, org_id)
    owner = await database.get(User, org.owner_user_id)
    if not await database.scalar(
        select(PlatformAdministrator).where(PlatformAdministrator.user_id == owner.id)
    ):
        database.add(PlatformAdministrator(id=1, user_id=owner.id))
        await database.flush()
    result = await app_context(
        ClerkPrincipal(owner.clerk_user_id, org.clerk_org_id, "org:admin"), database
    )
    assert result.active_org_registered
    assert result.platform_admin
    assert not result.can_create_org
    assert "configure" in result.capabilities
    owner.disabled_at = datetime.now(UTC)
    await database.flush()
    if not await database.scalar(
        select(PlatformAdministrator).where(PlatformAdministrator.user_id == owner.id)
    ):
        database.add(PlatformAdministrator(id=1, user_id=owner.id))
        await database.flush()
    result = await app_context(
        ClerkPrincipal(owner.clerk_user_id, org.clerk_org_id, "org:admin"), database
    )
    assert result.user_disabled and result.capabilities == []


async def test_text_tests_are_excluded_and_expired_ownership_is_uncertain(
    client, database, static_agent
):
    from voice_api.models import RuntimeAssignment
    from voice_api.services.runtime_recovery import recover_expired_assignments

    org_id = database.sync_session.info["organization_scope_id"]
    rows = [
        Run(
            id=new_id(),
            agent_version_id=static_agent["version_id"],
            channel=channel,
            status="running",
            resolved_config={},
            contact_snapshot={},
        )
        for channel in ("browser", "text_test")
    ]
    database.add_all(rows)
    await database.flush()
    assignment = RuntimeAssignment(
        run_id=rows[0].id,
        org_id=org_id,
        generation=new_id(),
        boot_id=new_id(),
        grant_hash="0" * 64,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        lease_expires_at=datetime.now(UTC) - timedelta(minutes=1),
        state="active",
    )
    database.add(assignment)
    await database.flush()
    response = await client.get(
        "/api/v1/runs", params={"agent_version_id": static_agent["version_id"]}
    )
    assert response.status_code == 200, response.text
    assert [r["id"] for r in response.json()["runs"]] == [rows[0].id]
    assert response.json()["runs"][0]["status"] == "uncertain"
    assert rows[0].ended_at is None and assignment.state == "uncertain"
    assert await recover_expired_assignments(database) == 0


async def test_draft_patch_accepts_generated_fact_tool_reference(client, static_agent):
    path = f"/api/v1/agent-versions/{static_agent['version_id']}"
    version = (await client.get(path)).json()
    config = version["config"]
    config["fact_slots"] = [
        {"key": "recepient_name", "description": "Caller name", "nodes": ["hello"]}
    ]
    config["flow"]["nodes"][0]["role_message"] = (
        "When given, call #record_recepient_name with the name."
    )
    response = await client.patch(path, json={"revision": version["revision"], "config": config})
    assert response.status_code == 200, response.text
    assert response.json()["revision"] == version["revision"] + 1
    assert "#record_recepient_name" in response.json()["config"]["flow"]["nodes"][0]["role_message"]
