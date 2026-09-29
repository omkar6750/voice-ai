from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from voice_api.api.deps import get_session, require_legacy_owner
from voice_api.core.security import allow_organization_member
from voice_api.db.tenant_scope import required_organization
from voice_api.models import WorkspaceSettings
from voice_api.schemas.workspace import WorkspaceResponse, WorkspaceUpdateRequest
from voice_runtime.contracts import WorkspaceConfig

router = APIRouter(tags=["workspace"])
Session = Depends(get_session)
Operator = Depends(require_legacy_owner)


@router.get("/workspace", response_model=WorkspaceResponse)
@allow_organization_member
async def workspace(session: AsyncSession = Session, _: None = Operator) -> WorkspaceResponse:
    org_id = required_organization(session.sync_session)
    row = await session.scalar(
        select(WorkspaceSettings).where(
            WorkspaceSettings.id == 1, WorkspaceSettings.org_id == org_id
        )
    )
    if row is None:
        row = WorkspaceSettings(
            id=1, org_id=org_id, config=WorkspaceConfig().model_dump(mode="json")
        )
        session.add(row)
        await session.commit()
    return WorkspaceResponse(
        revision=row.revision,
        config=WorkspaceConfig.model_validate(row.config),
    )


@router.patch("/workspace", response_model=WorkspaceResponse)
async def update_workspace(
    body: WorkspaceUpdateRequest,
    session: AsyncSession = Session,
    _: None = Operator,
) -> WorkspaceResponse:
    org_id = required_organization(session.sync_session)
    row = await session.scalar(
        select(WorkspaceSettings)
        .where(WorkspaceSettings.id == 1, WorkspaceSettings.org_id == org_id)
        .with_for_update()
    )
    if row is None:
        row = WorkspaceSettings(id=1, org_id=org_id, revision=1)
        session.add(row)
    if row.revision != body.revision:
        raise HTTPException(409, "Workspace changed by another operator")
    row.config = WorkspaceConfig.model_validate(body.config).model_dump(mode="json")
    row.revision += 1
    await session.commit()
    return WorkspaceResponse(revision=row.revision, config=body.config)
