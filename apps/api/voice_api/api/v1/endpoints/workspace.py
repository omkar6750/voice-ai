from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from voice_api.api.deps import get_session, require_legacy_owner
from voice_api.models import WorkspaceSettings
from voice_api.schemas.agent import RevisionBody
from voice_runtime.contracts import WorkspaceConfig

router = APIRouter(tags=["workspace"])
Session = Depends(get_session)
Operator = Depends(require_legacy_owner)


@router.get("/workspace")
async def workspace(session: AsyncSession = Session, _: None = Operator) -> dict:
    row = await session.get(WorkspaceSettings, 1)
    if row is None:
        row = WorkspaceSettings(id=1, config=WorkspaceConfig().model_dump(mode="json"))
        session.add(row)
        await session.commit()
    return {
        "revision": row.revision,
        "config": WorkspaceConfig.model_validate(row.config).model_dump(mode="json"),
    }


@router.patch("/workspace")
async def update_workspace(
    body: RevisionBody, session: AsyncSession = Session, _: None = Operator
) -> dict:
    row = await session.get(WorkspaceSettings, 1, with_for_update=True)
    if row is None:
        row = WorkspaceSettings(id=1, revision=1)
        session.add(row)
    if row.revision != body.revision:
        raise HTTPException(409, "Workspace changed by another operator")
    row.config = WorkspaceConfig.model_validate(body.config).model_dump(mode="json")
    row.revision += 1
    await session.commit()
    return {"revision": row.revision, "config": row.config}
