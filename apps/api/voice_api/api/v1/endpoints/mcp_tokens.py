"""Dashboard-only token lifecycle, never exposed as MCP tools."""

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from voice_api.core.clerk_auth import require_clerk_user
from voice_api.core.clerk_organizations import get_clerk_organization_directory
from voice_api.db.session import get_session
from voice_api.models import User
from voice_api.models.mcp import McpAudit, McpToken
from voice_api.services.mcp_auth import connection_info, issue

from .organizations import _registered_org

router = APIRouter(prefix="/orgs/{org_id}/mcp-tokens", tags=["mcp-access"])
Principal = Depends(require_clerk_user)
Session = Depends(get_session)
Directory = Depends(get_clerk_organization_directory)


class TokenCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80, pattern=r"^[\w .-]+$")
    days: Literal[7, 30, 90] = 30


class TokenView(BaseModel):
    id: str
    name: str
    user_id: str
    environment: str
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    last_used_at: datetime | None
    model_config = ConfigDict(from_attributes=True)


class ConnectionView(BaseModel):
    url: str
    environment: str
    env_var: str
    command: str


class TokenIssued(BaseModel):
    token: str
    metadata: TokenView
    connection: ConnectionView


async def access(
    request: Request, org_id: str, principal=Principal, session=Session, directory=Directory
):
    if request.headers.get("x-platform-support-session"):
        raise HTTPException(403, "MCP tokens require direct organization membership")
    org, membership = await _registered_org(org_id, session, directory, principal)
    if membership.role not in {"org:member", "org:admin", "org:owner"}:
        raise HTTPException(403, "Organization access required")
    user = await session.scalar(select(User).where(User.clerk_user_id == principal.user_id))
    if user is None or user.disabled_at:
        raise HTTPException(403, "Account access unavailable")
    return org, membership, user


Access = Depends(access)


@router.get("", response_model=list[TokenView])
async def list_tokens(response: Response, identity=Access, session=Session):
    org, membership, user = identity
    response.headers["Cache-Control"] = "no-store"
    query = (
        select(McpToken)
        .where(McpToken.organization_id == org.id)
        .order_by(McpToken.created_at.desc())
    )
    if membership.role == "org:member":
        query = query.where(McpToken.user_id == user.id)
    return (await session.scalars(query)).all()


@router.get("/connection", response_model=ConnectionView)
async def connection(identity=Access):
    return connection_info(identity[0].clerk_org_id)


@router.post("", response_model=TokenIssued, status_code=201)
async def create_token(body: TokenCreate, response: Response, identity=Access, session=Session):
    org, _, user = identity
    info = connection_info(org.clerk_org_id)
    row, raw = await issue(session, user, org, body.name, body.days)
    response.headers["Cache-Control"] = "no-store"
    return {"token": raw, "metadata": row, "connection": info}


@router.delete("/{token_id}", status_code=204)
async def revoke_token(token_id: str, identity=Access, session=Session):
    org, membership, user = identity
    row = await session.scalar(
        select(McpToken)
        .where(McpToken.id == token_id, McpToken.organization_id == org.id)
        .with_for_update()
    )
    if row is None or (membership.role == "org:member" and row.user_id != user.id):
        raise HTTPException(404, "MCP token not found")
    row.revoked_at = row.revoked_at or datetime.now(UTC)
    session.add(
        McpAudit(
            organization_id=org.id,
            actor_user_id=user.id,
            token_id=row.id,
            operation="token.revoke",
            outcome="success",
            targets={},
        )
    )
    await session.commit()
