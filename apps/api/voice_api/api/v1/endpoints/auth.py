"""Signed-in identity endpoint, organization access summary, and Clerk webhooks."""

import base64
import hashlib
import hmac
import json
import time
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from voice_api.core.clerk_auth import ClerkPrincipal, require_clerk_user
from voice_api.core.clerk_organizations import (
    ClerkOrganizationDirectory,
    get_clerk_organization_directory,
)
from voice_api.core.config import get_settings
from voice_api.core.security import (
    allow_organization_member,
    require_legacy_data_access,
    require_organization_access,
)
from voice_api.db.session import get_session
from voice_api.models import (
    ClerkWebhookEvent,
    Organization,
    OrganizationCreationClaim,
    PlatformAdministrator,
    User,
)

router = APIRouter(prefix="/auth", tags=["auth"])
Principal = Depends(require_clerk_user)
Owner = Depends(require_legacy_data_access)
Session = Depends(get_session)
Directory = Depends(get_clerk_organization_directory)
OrganizationAccess = Depends(require_organization_access)


def _verify_clerk_webhook(body: bytes, event_id: str | None, timestamp: str | None, signature: str | None) -> bool:
    secret = get_settings().clerk_webhook_signing_secret
    if not secret or not event_id or not timestamp or not signature:
        return False
    try:
        timestamp_value = int(timestamp)
    except ValueError:
        return False
    if abs(time.time() - timestamp_value) > 300:
        return False
    encoded_secret = secret.removeprefix("whsec_")
    try:
        key = base64.b64decode(encoded_secret)
    except ValueError:
        return False
    signed = f"{event_id}.{timestamp}.".encode() + body
    expected = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()
    return any(
        hmac.compare_digest(expected, value.removeprefix("v1,"))
        for value in signature.split()
    )


@router.post("/clerk/webhook", status_code=204)
async def clerk_webhook(
    request: Request,
    session: AsyncSession = Session,
    event_id: str | None = Header(default=None, alias="svix-id"),
    timestamp: str | None = Header(default=None, alias="svix-timestamp"),
    signature: str | None = Header(default=None, alias="svix-signature"),
) -> None:
    body = await request.body()
    if not _verify_clerk_webhook(body, event_id, timestamp, signature):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid Clerk webhook signature")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid webhook payload") from exc
    if not isinstance(payload, dict) or not event_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid webhook payload")
    inserted = await session.execute(
        pg_insert(ClerkWebhookEvent)
        .values(event_id=event_id)
        .on_conflict_do_nothing(index_elements=[ClerkWebhookEvent.event_id])
        .returning(ClerkWebhookEvent.event_id)
    )
    if inserted.scalar_one_or_none() is None:
        return
    if payload.get("type") == "user.deleted":
        clerk_user_id = (payload.get("data") or {}).get("id")
        if clerk_user_id:
            await session.execute(
                User.__table__.update()
                .where(User.clerk_user_id == clerk_user_id)
                .values(disabled_at=func.now())
            )
    await session.commit()


class AppContextView(BaseModel):
    """Small local application projection for the active Clerk organization."""

    user_id: str
    active_org_id: str | None
    active_org_name: str | None
    active_org_registered: bool
    active_org_role: Literal["org:admin", "org:member"] | None
    is_owner: bool
    platform_admin: bool
    user_disabled: bool
    can_create_org: bool
    organization_creation_enabled: bool
    capabilities: list[str]


@router.get("/context", response_model=AppContextView)
async def app_context(
    principal: ClerkPrincipal = Principal,
    session: AsyncSession = Session,
    directory: ClerkOrganizationDirectory = Directory,
) -> AppContextView:
    """Return only local product state for Clerk's current active org.

    Clerk owns identity, memberships, and organization selection. Resolve the
    current membership live here as well; the token's role is never authority.
    Protected resource endpoints repeat their own live authorization checks.
    """
    # Await Clerk before opening a database read transaction.
    membership = (
        await directory.membership(principal.org_id, principal.user_id)
        if principal.org_id
        else None
    )
    user = await session.scalar(select(User).where(User.clerk_user_id == principal.user_id))
    disabled = bool(user and user.disabled_at is not None)
    platform_admin = bool(
        user and not disabled
        and await session.scalar(
            select(PlatformAdministrator.user_id).where(PlatformAdministrator.user_id == user.id)
        )
    )
    organization = (
        await session.scalar(
            select(Organization).where(Organization.clerk_org_id == principal.org_id)
        )
        if principal.org_id
        else None
    )
    claimed = bool(
        user
        and await session.scalar(
            select(OrganizationCreationClaim.user_id).where(
                OrganizationCreationClaim.user_id == user.id
            )
        )
    )
    owned = bool(
        user
        and await session.scalar(select(Organization.id).where(Organization.owner_user_id == user.id))
    )
    role = None
    if not disabled and membership and membership.role in {"org:owner", "org:admin", "org:member"}:
        role = "org:admin" if membership.role == "org:owner" else membership.role
    is_owner = bool(
        organization is not None
        and user is not None
        and organization.owner_user_id == user.id
        and role == "org:admin"
        and not disabled
    )
    capabilities = []
    if organization is not None and role is not None and not disabled:
        capabilities = ["read", "browser_test"]
        if role == "org:admin":
            capabilities.extend(["manage_members", "configure"])
    return AppContextView(
        user_id=principal.user_id,
        active_org_id=principal.org_id,
        active_org_name=organization.name if organization else None,
        active_org_registered=organization is not None,
        active_org_role=role,
        is_owner=is_owner,
        platform_admin=platform_admin,
        user_disabled=disabled,
        can_create_org=not disabled and not claimed and not owned,
        organization_creation_enabled=get_settings().organization_creation_enabled,
        capabilities=capabilities,
    )


@router.get("/legacy-access", status_code=204)
@allow_organization_member
async def legacy_access(_: ClerkPrincipal = Owner) -> None:
    return None


@router.get("/organization-access", status_code=204)
@allow_organization_member
async def organization_access(
    _: ClerkPrincipal = OrganizationAccess,
) -> None:
    """Confirm that the active Clerk organization is registered and accessible."""
    return None
