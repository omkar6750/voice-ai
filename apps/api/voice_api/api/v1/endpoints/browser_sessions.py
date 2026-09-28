"""Browser sessions API endpoints for testing voice agents via WebRTC."""

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession
from voice_api.api.deps import get_session, require_legacy_owner
from voice_api.core.config import Settings, get_settings
from voice_api.schemas.browser_session import (
    BrowserSessionResponse,
    CreateBrowserSessionRequest,
    WebRTCOfferRequest,
    WebRTCPatchRequest,
)
from voice_api.services.browser_session_service import (
    create_browser_session,
    end_browser_session,
    handle_browser_offer,
    handle_browser_patch,
)

router = APIRouter(prefix="/browser-sessions", tags=["browser-sessions"])
Session = Depends(get_session)
Operator = Depends(require_legacy_owner)
Config = Depends(get_settings)


@router.post("", status_code=201, response_model=BrowserSessionResponse)
async def create_session(
    body: CreateBrowserSessionRequest | None = None,
    session: AsyncSession = Session,
    _: None = Operator,
) -> BrowserSessionResponse:
    req = body or CreateBrowserSessionRequest()
    run, browser_session = await create_browser_session(
        session=session,
        agent_id=req.agent_id,
        agent_version_id=req.agent_version_id,
        contact_id=req.contact_id,
        phone_number=req.phone_number,
        contact_variables=req.contact_variables,
        logging_override=req.logging_override,
    )
    return BrowserSessionResponse(
        id=browser_session.id,
        run_id=run.id,
        status=browser_session.status,
        contact_id=run.contact_id,
        created_at=browser_session.created_at,
        expires_at=browser_session.expires_at,
    )


@router.post("/{session_id}/offer")
async def post_offer(
    session_id: str,
    body: WebRTCOfferRequest,
    session: AsyncSession = Session,
    settings: Settings = Config,
    _: None = Operator,
) -> dict:
    return await handle_browser_offer(
        session_id=session_id,
        body=body,
        settings=settings,
        session=session,
    )


@router.patch("/{session_id}/offer")
async def patch_offer(
    session_id: str,
    body: WebRTCPatchRequest,
    _: None = Operator,
) -> Response:
    await handle_browser_patch(session_id=session_id, body=body)
    return Response(status_code=204)


@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    session: AsyncSession = Session,
    _: None = Operator,
) -> dict:
    return await end_browser_session(session_id=session_id, session=session)
