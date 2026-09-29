"""Browser sessions API endpoints for testing voice agents via WebSocket."""

from fastapi import APIRouter, Depends, WebSocket
from sqlalchemy.ext.asyncio import AsyncSession
from voice_api.api.deps import get_session, require_legacy_owner
from voice_api.core.config import get_settings
from voice_api.core.security import allow_organization_member
from voice_api.schemas.browser_session import (
    BrowserSessionResponse,
    CreateBrowserSessionRequest,
)
from voice_api.services.browser_session_service import (
    create_browser_session,
    end_browser_session,
    handle_browser_socket,
    issue_browser_ticket,
)

router = APIRouter(prefix="/browser-sessions", tags=["browser-sessions"])
Session = Depends(get_session)
Operator = Depends(require_legacy_owner)


@router.post("", status_code=201, response_model=BrowserSessionResponse)
@allow_organization_member
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
        sample_rate=run.resolved_config.get("audio", {}).get("sample_rate", 16000),
    )


@router.post("/{session_id}/ticket")
@allow_organization_member
async def post_ticket(
    session_id: str,
    session: AsyncSession = Session,
    _: None = Operator,
) -> dict:
    return await issue_browser_ticket(session_id, session)


@router.websocket("/{session_id}/ws")
async def browser_socket(session_id: str, websocket: WebSocket) -> None:
    await handle_browser_socket(session_id, websocket, get_settings())


@router.delete("/{session_id}")
@allow_organization_member
async def delete_session(
    session_id: str,
    session: AsyncSession = Session,
    _: None = Operator,
) -> dict:
    return await end_browser_session(session_id=session_id, session=session)
