"""Signed-in identity endpoint, organization access summary, and Clerk webhooks."""

import base64
import hashlib
import hmac
import json
import time

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
    LegacyDataTenant,
    Organization,
    OrganizationCreationClaim,
    PlatformAdministrator,
    User,
)
from voice_api.models.common import new_id

router = APIRouter(prefix="/auth", tags=["auth"])
account_router = APIRouter(tags=["auth"])
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


class AccountOrganization(BaseModel):
    id: str
    name: str
    role: str
    registered: bool
    is_owner: bool
    capabilities: list[str]


class AccountView(BaseModel):
    user_id: str
    active_org_id: str | None
    platform_admin: bool
    can_create_org: bool
    organization_creation_enabled: bool
    organizations: list[AccountOrganization]


@router.get("/me")
async def me(principal: ClerkPrincipal = Principal) -> dict:
    return {"user_id": principal.user_id, "org_id": principal.org_id}


@account_router.get("/me", response_model=AccountView)
async def account(
    principal: ClerkPrincipal = Principal,
    session: AsyncSession = Session,
    directory: ClerkOrganizationDirectory = Directory,
) -> AccountView:
    profile = await directory.verified_profile(principal.user_id)
    await session.execute(
        pg_insert(User)
        .values(
            id=new_id(),
            clerk_user_id=principal.user_id,
            primary_verified_email=profile["email"],
            first_name=profile["first_name"],
            last_name=profile["last_name"],
        )
        .on_conflict_do_update(
            index_elements=[User.clerk_user_id],
            set_={
                "primary_verified_email": profile["email"],
                "first_name": profile["first_name"],
                "last_name": profile["last_name"],
                "updated_at": func.now(),
            },
        )
    )
    await session.commit()
    memberships = await directory.joined(principal.user_id)
    ids = [item.clerk_org_id for item in memberships]
    local_rows = (
        (
            await session.scalars(select(Organization).where(Organization.clerk_org_id.in_(ids)))
        ).all()
        if ids
        else []
    )
    local = {item.clerk_org_id: item for item in local_rows}
    user = await session.scalar(select(User).where(User.clerk_user_id == principal.user_id))
    claimed = owned = platform_admin = False
    if user is not None:
        claimed = (
            await session.scalar(
                select(OrganizationCreationClaim.user_id).where(
                    OrganizationCreationClaim.user_id == user.id
                )
            )
            is not None
        )
        owned = (
            await session.scalar(
                select(Organization.id).where(Organization.owner_user_id == user.id)
            )
            is not None
        )
        platform_admin = (
            await session.scalar(
                select(PlatformAdministrator.user_id).where(
                    PlatformAdministrator.user_id == user.id
                )
            )
            is not None
        )
    legacy_org_id = await session.scalar(select(LegacyDataTenant.organization_id))
    organizations = []
    for membership in memberships:
        organization = local.get(membership.clerk_org_id)
        capabilities = []
        if organization is not None:
            capabilities.extend(["read", "browser_test"])
            if membership.role == "org:admin":
                capabilities.extend(["manage_members", "configure"])
                if organization.id == legacy_org_id:
                    capabilities.append("twilio_dial")
            if user and organization.owner_user_id == user.id:
                capabilities.append("transfer_ownership")
        organizations.append(
            AccountOrganization(
                id=membership.clerk_org_id,
                name=membership.name,
                role=membership.role,
                registered=organization is not None,
                is_owner=bool(user and organization and organization.owner_user_id == user.id),
                capabilities=capabilities,
            )
        )
    return AccountView(
        user_id=principal.user_id,
        active_org_id=principal.org_id,
        platform_admin=platform_admin,
        can_create_org=not claimed and not owned,
        organization_creation_enabled=get_settings().organization_creation_enabled,
        organizations=organizations,
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
