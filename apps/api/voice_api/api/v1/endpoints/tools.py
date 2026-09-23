from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from voice_api.api.deps import get_session, require_operator
from voice_api.models import Tool, ToolVersion
from voice_api.models.common import new_id
from voice_api.schemas.agent import CreateBody, ExpectedRevision, RevisionBody
from voice_api.services.publication_service import clone_version
from voice_runtime.contracts import ToolConfig

router = APIRouter(tags=["tools"])
Session = Depends(get_session)
Operator = Depends(require_operator)


@router.get("/tools")
async def tools(session: AsyncSession = Session, _: None = Operator) -> dict:
    rows = (await session.scalars(select(Tool).order_by(Tool.name))).all()
    return {"tools": [{"id": row.id, "name": row.name} for row in rows]}


@router.post("/tools", status_code=201)
async def create_tool(
    body: CreateBody, session: AsyncSession = Session, _: None = Operator
) -> dict:
    config = ToolConfig.model_validate(body.config).model_dump(mode="json")
    if config["name"] != body.name:
        raise HTTPException(422, "Tool name must match configuration name")
    tool = Tool(id=new_id(), name=body.name)
    version = ToolVersion(id=new_id(), tool_id=tool.id, version=1, config=config)
    session.add(tool)
    await session.flush()
    session.add(version)
    await session.commit()
    return {"tool_id": tool.id, "version_id": version.id}


@router.get("/tools/{tool_id}/versions")
async def tool_versions(tool_id: str, session: AsyncSession = Session, _: None = Operator) -> dict:
    rows = (
        await session.scalars(
            select(ToolVersion).where(ToolVersion.tool_id == tool_id).order_by(ToolVersion.version)
        )
    ).all()
    return {
        "versions": [
            {
                "id": row.id,
                "version": row.version,
                "revision": row.revision,
                "status": row.status,
                "config": row.config,
            }
            for row in rows
        ]
    }


@router.patch("/tool-versions/{version_id}")
async def update_tool_version(
    version_id: str, body: RevisionBody, session: AsyncSession = Session, _: None = Operator
) -> dict:
    row = await session.get(ToolVersion, version_id, with_for_update=True)
    if row is None:
        raise HTTPException(404, "Tool version not found")
    if row.status != "draft":
        raise HTTPException(409, "Published versions are immutable")
    if row.revision != body.revision:
        raise HTTPException(409, "Draft changed by another operator")
    row.config = ToolConfig.model_validate(body.config).model_dump(mode="json")
    row.revision += 1
    await session.commit()
    return {"id": row.id, "revision": row.revision, "config": row.config}


@router.post("/tool-versions/{version_id}/publish")
async def publish_tool(
    version_id: str, body: ExpectedRevision, session: AsyncSession = Session, _: None = Operator
) -> dict:
    row = await session.get(ToolVersion, version_id, with_for_update=True)
    if row is None:
        raise HTTPException(404, "Tool version not found")
    if row.status != "draft":
        raise HTTPException(409, "Version is already published")
    ToolConfig.model_validate(row.config)
    if row.revision != body.revision:
        raise HTTPException(409, "Draft changed; reload before publishing")
    row.status, row.published_at = "published", datetime.now(UTC)
    await session.commit()
    return {"id": row.id, "status": row.status}


@router.post("/tool-versions/{version_id}/clone", status_code=201)
async def clone_tool(
    version_id: str, body: ExpectedRevision, session: AsyncSession = Session, _: None = Operator
) -> dict:
    return await clone_version(session, version_id, "tool", body.revision)
