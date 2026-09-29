"""Database-assigned platform administration endpoints."""

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from voice_api.core.clerk_auth import ClerkPrincipal, require_clerk_user
from voice_api.db.session import get_session
from voice_api.models import (
    Organization,
    OrganizationAudit,
    PlatformAdministrator,
    PlatformSupportSession,
    User,
)

router = APIRouter(prefix="/platform", tags=["platform administration"])
Principal = Depends(require_clerk_user)
Session = Depends(get_session)


class PlatformOrganizationView(BaseModel):
    id: str
    name: str
    owner_user_id: str
    owner_name: str | None


class PlatformSupportSessionView(BaseModel):
    token: str
    organization_id: str
    expires_at: datetime


async def _require_platform_admin(
    principal: ClerkPrincipal,
    session: AsyncSession,
) -> User:
    user = await session.scalar(
        select(User).where(
            User.clerk_user_id == principal.user_id,
            User.disabled_at.is_(None),
        )
    )
    if user is None:
        raise HTTPException(403, "Platform administrator required")
    assignment = await session.scalar(
        select(PlatformAdministrator.id).where(PlatformAdministrator.user_id == user.id)
    )
    if assignment is None:
        raise HTTPException(403, "Platform administrator required")
    return user


@router.get("/orgs", response_model=list[PlatformOrganizationView])
async def platform_organizations(
    principal: ClerkPrincipal = Principal,
    session: AsyncSession = Session,
) -> list[PlatformOrganizationView]:
    """List registered customer orgs; this does not grant access to their data."""
    await _require_platform_admin(principal, session)
    rows = (
        await session.execute(
            select(Organization, User)
            .join(User, User.id == Organization.owner_user_id)
            .order_by(Organization.name, Organization.id)
        )
    ).all()
    return [
        PlatformOrganizationView(
            id=organization.clerk_org_id,
            name=organization.name,
            owner_user_id=owner.clerk_user_id,
            owner_name=" ".join(part for part in (owner.first_name, owner.last_name) if part)
            or None,
        )
        for organization, owner in rows
    ]


@router.post("/orgs/{org_id}/support-session", response_model=PlatformSupportSessionView)
async def start_support_session(
    org_id: str,
    principal: ClerkPrincipal = Principal,
    session: AsyncSession = Session,
) -> PlatformSupportSessionView:
    """Start a 30-minute audited support session for one registered organization."""
    actor = await _require_platform_admin(principal, session)
    organization = await session.scalar(
        select(Organization).where(Organization.clerk_org_id == org_id)
    )
    if organization is None:
        raise HTTPException(404, "Organization not found")

    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=30)
    token = token_urlsafe(32)
    token_hash = sha256(token.encode("utf-8")).hexdigest()
    await session.execute(
        update(PlatformSupportSession)
        .where(
            PlatformSupportSession.user_id == actor.id,
            PlatformSupportSession.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    session.add(
        PlatformSupportSession(
            token_hash=token_hash,
            user_id=actor.id,
            organization_id=organization.id,
            expires_at=expires_at,
        )
    )
    session.add(
        OrganizationAudit(
            organization_id=organization.id,
            actor_user_id=actor.id,
            action="platform_support_started",
        )
    )
    await session.commit()
    return PlatformSupportSessionView(
        token=token,
        organization_id=org_id,
        expires_at=expires_at,
    )


@router.delete("/support-session", status_code=204)
async def end_support_session(
    principal: ClerkPrincipal = Principal,
    session: AsyncSession = Session,
    support_token: str | None = Header(default=None, alias="X-Platform-Support-Session"),
) -> None:
    actor = await _require_platform_admin(principal, session)
    if not support_token or len(support_token) > 256:
        raise HTTPException(404, "Support session not found")
    token_hash = sha256(support_token.encode("utf-8")).hexdigest()
    support_session = await session.get(PlatformSupportSession, token_hash)
    if (
        support_session is None
        or support_session.user_id != actor.id
        or support_session.revoked_at is not None
    ):
        raise HTTPException(404, "Support session not found")
    support_session.revoked_at = datetime.now(UTC)
    session.add(
        OrganizationAudit(
            organization_id=support_session.organization_id,
            actor_user_id=actor.id,
            action="platform_support_ended",
        )
    )
    await session.commit()
