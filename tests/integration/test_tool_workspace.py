"""Additive read contracts and existing tool mutation behavior."""

from voice_api.models import (
    Agent,
    AgentVersion,
    AgentVersionTool,
    Organization,
    Tool,
    ToolVersion,
    User,
)
from voice_api.models.common import new_id


async def make_tool(client):
    name = "ux_" + new_id().replace("-", "")
    config = {
        "name": name,
        "description": "Original description",
        "kind": "registered",
        "handler": "end_call",
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "properties": {"reason": {"type": "string", "enum": ["done", "busy"]}},
        },
    }
    response = await client.post("/api/v1/tools", json={"name": name, "config": config})
    assert response.status_code == 201, response.text
    return response.json(), config


async def test_tool_save_clone_publish_keep_exact_bindings(client, database):
    ids, config = await make_tool(client)
    version_id, tool_id = ids["version_id"], ids["tool_id"]
    config["description"] = "Saved description"
    saved = await client.patch(
        f"/api/v1/tool-versions/{version_id}", json={"revision": 1, "config": config}
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["revision"] == 2
    assert saved.json()["config"]["parameters"] == config["parameters"]
    stale = await client.patch(
        f"/api/v1/tool-versions/{version_id}", json={"revision": 1, "config": config}
    )
    assert stale.status_code == 409
    stale_publish = await client.post(
        f"/api/v1/tool-versions/{version_id}/publish", json={"revision": 1}
    )
    assert stale_publish.status_code == 409
    checked = await client.post(f"/api/v1/tool-versions/{version_id}/validate")
    assert checked.json()["valid"] is True
    assert checked.json()["revision"] == 2
    published = await client.post(
        f"/api/v1/tool-versions/{version_id}/publish", json={"revision": 2}
    )
    assert published.status_code == 200, published.text
    immutable = await client.patch(
        f"/api/v1/tool-versions/{version_id}", json={"revision": 2, "config": config}
    )
    assert immutable.status_code == 409

    agent = Agent(id=new_id(), name="Workspace binding test")
    database.add(agent)
    await database.flush()
    agent_version = AgentVersion(
        id=new_id(),
        agent_id=agent.id,
        version=1,
        config={
            "name": "Workspace binding test",
            "flow": {"initial_node": "start", "nodes": [{"id": "start", "terminal": True}]},
            "tool_bindings": {"finish": {"tool_id": tool_id, "tool_version_id": version_id}},
        },
    )
    database.add(agent_version)
    await database.flush()
    binding = AgentVersionTool(
        agent_version_id=agent_version.id, binding_key="finish", tool_version_id=version_id
    )
    database.add(binding)
    await database.flush()

    clones = []
    for _ in range(2):
        response = await client.post(
            f"/api/v1/tool-versions/{version_id}/clone", json={"revision": 2}
        )
        assert response.status_code == 201, response.text
        clones.append(response.json()["id"])
    assert clones[0] != clones[1]
    cloned = await client.get(f"/api/v1/tool-versions/{clones[0]}?tool_id={tool_id}")
    assert cloned.json()["config"] == saved.json()["config"]
    newer_publish = await client.post(
        f"/api/v1/tool-versions/{clones[0]}/publish", json={"revision": 1}
    )
    assert newer_publish.status_code == 200
    usage = await client.get(f"/api/v1/tools/{tool_id}/usage")
    assert usage.status_code == 200, usage.text
    assert usage.json()["bindings"] == [
        {
            "agent_id": agent.id,
            "agent_name": agent.name,
            "agent_version_id": agent_version.id,
            "agent_version": 1,
            "agent_status": "draft",
            "binding_key": "finish",
            "tool_id": tool_id,
            "tool_version_id": version_id,
            "tool_version": 1,
        }
    ]
    await database.refresh(binding)
    assert binding.tool_version_id == version_id


async def test_summary_pagination_preserves_full_version_contract(client):
    ids, _ = await make_tool(client)
    tool_id, version_id = ids["tool_id"], ids["version_id"]
    for _ in range(5):
        response = await client.post(
            f"/api/v1/tool-versions/{version_id}/clone", json={"revision": 1}
        )
        assert response.status_code == 201
    full = await client.get(f"/api/v1/tools/{tool_id}/versions")
    assert len(full.json()["versions"]) == 6
    assert [row["version"] for row in full.json()["versions"]] == list(range(1, 7))
    assert all("config" in row for row in full.json()["versions"])
    page = await client.get(f"/api/v1/tools/{tool_id}/versions?view=summary&limit=2")
    assert page.status_code == 200, page.text
    assert [row["version"] for row in page.json()["versions"]] == [6, 5]
    assert page.json()["next_before_version"] == 5
    assert all("config" not in row for row in page.json()["versions"])
    assert all(row["parent_version"] == 1 for row in page.json()["versions"])
    second = await client.get(
        f"/api/v1/tools/{tool_id}/versions?view=summary&limit=2&before_version=5"
    )
    assert [row["version"] for row in second.json()["versions"]] == [4, 3]
    empty = await client.get(f"/api/v1/tools/{tool_id}/versions?view=summary&status=published")
    assert empty.json()["versions"] == []
    catalog = await client.get("/api/v1/tools?view=summary")
    summary = next(row for row in catalog.json()["tools"] if row["id"] == tool_id)
    assert summary["draft_count"] == 6
    assert summary["latest_published_version"] is None
    original_catalog = await client.get("/api/v1/tools")
    assert set(next(row for row in original_catalog.json()["tools"] if row["id"] == tool_id)) == {
        "id",
        "name",
    }
    invalid = await client.get(f"/api/v1/tools/{tool_id}/versions?view=summary&limit=101")
    assert invalid.status_code == 422
    wrong_tool = await client.get(f"/api/v1/tool-versions/{version_id}?tool_id=wrong")
    assert wrong_tool.status_code == 404


async def test_new_tool_reads_never_expose_another_organization(client, database):
    owner = User(id=new_id(), clerk_user_id="user_" + new_id())
    database.add(owner)
    await database.flush()
    other = Organization(
        id=new_id(),
        clerk_org_id="org_" + new_id(),
        name="Other organization",
        owner_user_id=owner.id,
    )
    database.add(other)
    await database.flush()
    tool_id, version_id = new_id(), new_id()
    connection = await database.connection()
    await connection.execute(
        Tool.__table__.insert().values(id=tool_id, org_id=other.id, name="foreign_tool")
    )
    await connection.execute(
        ToolVersion.__table__.insert().values(
            id=version_id,
            org_id=other.id,
            tool_id=tool_id,
            version=1,
            config={"name": "foreign_tool", "kind": "registered", "handler": "end_call"},
        )
    )
    catalog = await client.get("/api/v1/tools?view=summary")
    assert tool_id not in {row["id"] for row in catalog.json()["tools"]}
    for path in (
        f"/api/v1/tools/{tool_id}/versions?view=summary",
        f"/api/v1/tools/{tool_id}/usage",
        f"/api/v1/tool-versions/{version_id}?tool_id={tool_id}",
    ):
        response = await client.get(path)
        assert response.status_code == 404, response.text
    full = await client.get(f"/api/v1/tools/{tool_id}/versions")
    assert full.json()["versions"] == []
