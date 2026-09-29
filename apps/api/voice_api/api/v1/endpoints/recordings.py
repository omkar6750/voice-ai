"""Current-membership recording access; support sessions cannot access recordings."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from voice_api.core.clerk_auth import ClerkPrincipal
from voice_api.core.security import allow_organization_member, require_organization_access
from voice_api.db.session import get_session
from voice_api.models.artifacts import RecordingDeletion, RunArtifact
from voice_api.schemas.recordings import (
    RecordingDeletionExecute,
    RecordingDeletionListResponse,
    RecordingDeletionPreviewResponse,
    RecordingDeletionResponse,
    RecordingDeletionSelection,
    RecordingListResponse,
    RecordingResponse,
)
from voice_api.services import recording_deletion as deletion

router = APIRouter(tags=["recordings"])
Session = Depends(get_session)
OrganizationAccess = Depends(require_organization_access)


async def require_recording_access(
    request: Request, principal: ClerkPrincipal = OrganizationAccess
) -> ClerkPrincipal:
    if request.headers.get("x-platform-support-session") or getattr(
        request.state, "platform_support_session", None
    ):
        raise HTTPException(403, "Recording access is unavailable in support mode")
    return principal


Access = Depends(require_recording_access)


@router.get("/recordings", response_model=RecordingListResponse)
@allow_organization_member
async def list_recordings(
    session: AsyncSession = Session,
    principal: ClerkPrincipal = Access,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    query = select(RunArtifact).where(RunArtifact.kind.in_(deletion.RECORDING_KINDS))
    total = await session.scalar(
        select(func.count())
        .select_from(RunArtifact)
        .where(RunArtifact.kind.in_(deletion.RECORDING_KINDS))
    )
    rows = (
        await session.scalars(
            query.order_by(RunArtifact.created_at.desc(), RunArtifact.id)
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return {"artifacts": [RecordingResponse.model_validate(row) for row in rows], "total": total}


@router.post("/recording-deletions/preview", response_model=RecordingDeletionPreviewResponse)
async def preview(
    body: RecordingDeletionSelection,
    session: AsyncSession = Session,
    principal: ClerkPrincipal = Access,
):
    return await deletion.preview(session, principal.user_id, body)


@router.post(
    "/recording-deletions/{operation_id}/execute", response_model=RecordingDeletionResponse
)
async def execute(
    operation_id: str,
    body: RecordingDeletionExecute,
    session: AsyncSession = Session,
    principal: ClerkPrincipal = Access,
):
    operation = await deletion.execute(
        session, operation_id, principal.user_id, body.confirmation_token, body.confirmation_text
    )
    return await deletion.progress(session, operation)


@router.post(
    "/recording-deletions/{operation_id}/continue", response_model=RecordingDeletionResponse
)
async def continue_operation(
    operation_id: str, session: AsyncSession = Session, principal: ClerkPrincipal = Access
):
    await deletion.continue_deletion(session, operation_id, principal.user_id)
    operation = await deletion.owned_operation(session, operation_id, principal.user_id)
    return await deletion.progress(session, operation)


@router.get("/recording-deletions", response_model=RecordingDeletionListResponse)
async def list_operations(session: AsyncSession = Session, principal: ClerkPrincipal = Access):
    operations = (
        await session.scalars(
            select(RecordingDeletion)
            .where(
                RecordingDeletion.actor_id == principal.user_id,
                RecordingDeletion.status != "preview",
            )
            .order_by(RecordingDeletion.created_at.desc())
            .limit(50)
        )
    ).all()
    return {"operations": [await deletion.progress(session, operation) for operation in operations]}


@router.get("/recording-deletions/{operation_id}", response_model=RecordingDeletionResponse)
async def get_operation(
    operation_id: str, session: AsyncSession = Session, principal: ClerkPrincipal = Access
):
    operation = await deletion.owned_operation(session, operation_id, principal.user_id)
    return await deletion.progress(session, operation)
