from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from voice_api.api.deps import get_session, require_legacy_owner
from voice_api.core.security import allow_organization_member
from voice_api.models import (
    Agent,
    AgentVersion,
    AgentVersionKnowledge,
    AgentVersionTool,
    CalendarIntegration,
    Callback,
    Run,
    ToolVersion,
)
from voice_api.models.common import new_id
from voice_api.schemas.agent import (
    ActivateAgentBody,
    BindToolBody,
    CreateBody,
    ExpectedRevision,
    RevisionBody,
)
from voice_api.services.publication_service import clone_version, sync_bindings
from voice_runtime.contracts import AgentConfig

router = APIRouter(tags=["agents"])
Session = Depends(get_session)
Operator = Depends(require_legacy_owner)


async def validate_callback_calendars(session: AsyncSession, config: AgentConfig) -> None:
    scheduling = config.callback_scheduling
    if not scheduling.enabled:
        return
    for person in scheduling.bookable_people:
        integration = await session.get(CalendarIntegration, person.calendar_integration_id)
        if integration is None:
            raise HTTPException(
                422, f"Bookable person '{person.name}' references a missing calendar integration"
            )
        if integration.provider != "google_calendar":
            raise HTTPException(
                422, f"Bookable person '{person.name}' references an unsupported calendar provider"
            )
        if integration.status != "connected":
            raise HTTPException(422, f"Calendar for '{person.name}' is not connected")


async def validate_agent_bindings(session: AsyncSession, version: AgentVersion) -> None:
    """Keep flow JSON references and relational pinned tool versions identical."""
    config = AgentConfig.model_validate(version.config)
    rows = (
        await session.scalars(
            select(AgentVersionTool).where(AgentVersionTool.agent_version_id == version.id)
        )
    ).all()
    database = {row.binding_key: row.tool_version_id for row in rows}
    configured = {key: value.tool_version_id for key, value in config.tool_bindings.items()}
    if database != configured:
        raise HTTPException(422, "Agent tool bindings do not match pinned tool versions")


@router.get("/agents")
@allow_organization_member
async def agents(session: AsyncSession = Session, _: None = Operator) -> dict:
    rows = (await session.scalars(select(Agent).order_by(Agent.name))).all()
    results = []
    for x in rows:
        latest = await session.scalar(
            select(AgentVersion)
            .where(AgentVersion.agent_id == x.id)
            .order_by(AgentVersion.version.desc())
        )
        results.append(
            {
                "id": x.id,
                "name": x.name,
                "active_version_id": x.active_version_id,
                "published_version_id": x.active_version_id,
                "latest_version_id": latest.id if latest else None,
                "latest_version_status": latest.status if latest else None,
            }
        )
    return {"agents": results}


@router.post("/agents", status_code=201)
async def create_agent(
    body: CreateBody, session: AsyncSession = Session, _: None = Operator
) -> dict:
    config_model = AgentConfig.model_validate(body.config)
    await validate_callback_calendars(session, config_model)
    config = config_model.model_dump(mode="json")
    agent = Agent(id=new_id(), name=body.name)
    version = AgentVersion(id=new_id(), agent_id=agent.id, version=1, config=config)
    session.add(agent)
    await session.flush()
    session.add(version)
    await session.flush()
    await sync_bindings(session, version)
    await session.commit()
    return {"agent_id": agent.id, "version_id": version.id}


@router.get("/agents/{agent_id}/versions")
@allow_organization_member
async def agent_versions(
    agent_id: str, session: AsyncSession = Session, _: None = Operator
) -> dict:
    rows = (
        await session.scalars(
            select(AgentVersion)
            .where(AgentVersion.agent_id == agent_id)
            .order_by(AgentVersion.version)
        )
    ).all()
    return {
        "versions": [
            {
                "id": x.id,
                "version": x.version,
                "revision": x.revision,
                "status": x.status,
                "config": x.config,
                "note": x.note,
            }
            for x in rows
        ]
    }


@router.patch("/agent-versions/{version_id}")
async def update_agent_version(
    version_id: str, body: RevisionBody, session: AsyncSession = Session, _: None = Operator
) -> dict:
    row = await session.get(AgentVersion, version_id, with_for_update=True)
    if row is None:
        raise HTTPException(404, "Agent version not found")
    if row.status != "draft":
        raise HTTPException(409, "Published versions are immutable")
    if row.revision != body.revision:
        raise HTTPException(409, "Draft changed by another operator")
    config_model = AgentConfig.model_validate(body.config)
    await validate_callback_calendars(session, config_model)
    row.config = config_model.model_dump(mode="json")
    row.note = body.note
    row.revision += 1
    await sync_bindings(session, row)
    await session.commit()
    return {"id": row.id, "revision": row.revision, "config": row.config}


@router.post("/agent-versions/{version_id}/publish")
async def publish_agent(
    version_id: str, body: ExpectedRevision, session: AsyncSession = Session, _: None = Operator
) -> dict:
    row = await session.get(AgentVersion, version_id, with_for_update=True)
    if row is None:
        raise HTTPException(404, "Agent version not found")
    if row.status != "draft":
        raise HTTPException(409, "Version is already published")
    config = AgentConfig.model_validate(row.config)
    await validate_callback_calendars(session, config)
    if row.revision != body.revision:
        raise HTTPException(409, "Draft changed; reload before publishing")
    await validate_agent_bindings(session, row)
    row.status = "published"
    row.published_at = datetime.now(UTC)
    await session.commit()
    return {"id": row.id, "status": row.status, "published_at": row.published_at}


@router.post("/agent-versions/{version_id}/clone", status_code=201)
async def clone_agent(
    version_id: str, body: ExpectedRevision, session: AsyncSession = Session, _: None = Operator
) -> dict:
    return await clone_version(session, version_id, "agent", body.revision)


@router.post("/agents/{agent_id}/activate")
async def activate_agent(
    agent_id: str,
    body: ActivateAgentBody | dict,
    session: AsyncSession = Session,
    _: None = Operator,
) -> dict:
    version_id = body.version_id if isinstance(body, ActivateAgentBody) else body.get("version_id")
    agent = await session.get(Agent, agent_id, with_for_update=True)
    version = await session.get(AgentVersion, version_id)
    if (
        agent is None
        or version is None
        or version.agent_id != agent_id
        or version.status != "published"
    ):
        raise HTTPException(422, "Select a published agent version")
    agent.active_version_id = version.id
    await session.commit()
    return {"active_version_id": agent.active_version_id}


@router.put("/agent-versions/{version_id}/tools")
async def bind_tool(
    version_id: str, body: BindToolBody, session: AsyncSession = Session, _: None = Operator
) -> dict:
    agent_version = await session.get(AgentVersion, version_id, with_for_update=True)
    tool_version = await session.get(ToolVersion, body.tool_version_id)
    if agent_version is None or tool_version is None or tool_version.status != "published":
        raise HTTPException(422, "Binding requires draft agent and published tool version")
    if agent_version.status != "draft":
        raise HTTPException(409, "Published agent versions are immutable")
    if agent_version.revision != body.revision:
        raise HTTPException(409, "Draft changed; reload before binding")
    row = await session.get(AgentVersionTool, (version_id, body.binding_key))
    if row is None:
        row = AgentVersionTool(
            agent_version_id=version_id,
            binding_key=body.binding_key,
            tool_version_id=tool_version.id,
            config=body.config,
        )
        session.add(row)
    else:
        row.tool_version_id, row.config = tool_version.id, body.config
    config = AgentConfig.model_validate(agent_version.config).model_dump(mode="json")
    config["tool_bindings"][body.binding_key] = {
        "tool_id": tool_version.tool_id,
        "tool_version_id": tool_version.id,
    }
    agent_version.config = config
    agent_version.revision += 1
    await session.commit()
    return {
        "binding_key": row.binding_key,
        "tool_version_id": row.tool_version_id,
        "revision": agent_version.revision,
    }


@router.get("/agents/{agent_id}/impact")
@allow_organization_member
async def agent_deletion_impact(
    agent_id: str, session: AsyncSession = Session, _: None = Operator
) -> dict:
    agent = await session.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(404, "Agent not found")

    v_rows = (
        await session.scalars(select(AgentVersion).where(AgentVersion.agent_id == agent_id))
    ).all()
    v_ids = [v.id for v in v_rows]

    run_count = 0
    if v_ids:
        run_count = (
            await session.scalar(select(func.count(Run.id)).where(Run.agent_version_id.in_(v_ids)))
        ) or 0

    warnings = []
    if run_count > 0:
        warnings.append(
            f"This agent has {run_count} historical call run(s). Deleting it will permanently delete run evidence and call transcripts."
        )
    if len(v_rows) > 0:
        warnings.append(
            f"All {len(v_rows)} version(s) (prompts, flows, node bindings, and knowledge attachments) will be permanently destroyed."
        )

    return {
        "agent_id": agent.id,
        "name": agent.name,
        "versions_count": len(v_rows),
        "runs_count": run_count,
        "can_delete": True,
        "warnings": warnings,
    }


@router.delete("/agents/{agent_id}")
async def delete_agent(
    agent_id: str,
    force: bool = False,
    session: AsyncSession = Session,
    _: None = Operator,
) -> dict:
    agent = await session.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(404, "Agent not found")

    v_rows = (
        await session.scalars(select(AgentVersion).where(AgentVersion.agent_id == agent_id))
    ).all()
    v_ids = [v.id for v in v_rows]

    run_count = 0
    if v_ids:
        run_count = (
            await session.scalar(select(func.count(Run.id)).where(Run.agent_version_id.in_(v_ids)))
        ) or 0

    if run_count > 0 and not force:
        raise HTTPException(
            400,
            f"Agent '{agent.name}' has {run_count} historical call runs. Set force=true to delete with evidence history.",
        )

    await session.execute(text("SET LOCAL session_replication_role = 'replica';"))

    if v_ids:
        await session.execute(delete(Callback).where(Callback.agent_version_id.in_(v_ids)))
        if run_count > 0:
            await session.execute(delete(Run).where(Run.agent_version_id.in_(v_ids)))

        await session.execute(
            delete(AgentVersionTool).where(AgentVersionTool.agent_version_id.in_(v_ids))
        )
        await session.execute(
            delete(AgentVersionKnowledge).where(AgentVersionKnowledge.agent_version_id.in_(v_ids))
        )
        await session.execute(delete(AgentVersion).where(AgentVersion.agent_id == agent_id))

    await session.execute(delete(Agent).where(Agent.id == agent_id))
    await session.commit()
    return {"status": "ok", "deleted_agent_id": agent_id, "name": agent.name}
