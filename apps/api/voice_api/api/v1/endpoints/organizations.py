"""Organization provisioning and product credential endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from pydantic import BaseModel, SecretStr, field_validator
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from voice_api.core.clerk_auth import ClerkPrincipal, require_clerk_user
from voice_api.core.clerk_organizations import (
    ClerkOrganizationDirectory,
    OrganizationMember,
    get_clerk_organization_directory,
)
from voice_api.core.config import get_settings
from voice_api.db.session import get_session
from voice_api.db.tenant_scope import bind_organization
from voice_api.models import (
    Organization,
    OrganizationAudit,
    OrganizationCreationClaim,
    ProviderCredential,
    User,
)
from voice_api.models.common import new_id
from voice_api.schemas.credentials import (
    CredentialCreate,
    CredentialDelete,
    CredentialRename,
    CredentialReplace,
    CredentialStatus,
)
from voice_api.services import credential_service
from voice_api.services.organization_seed import seed_organization

router = APIRouter(prefix="/orgs", tags=["organizations"])
Principal = Depends(require_clerk_user)
Session = Depends(get_session)
Directory = Depends(get_clerk_organization_directory)


class OrganizationView(BaseModel):
    id: str
    name: str
    role: str
    is_owner: bool
    registered: bool


class CreateOrganizationBody(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        name = value.strip()
        if not 2 <= len(name) <= 120 or "<" in name or ">" in name:
            raise ValueError("Organization name must be 2-120 characters and contain no HTML")
        return name


class ProviderCredentialBody(BaseModel):
    api_key: SecretStr

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, value: SecretStr) -> SecretStr:
        key = value.get_secret_value().strip()
        if not key or len(key) > 4096:
            raise ValueError("Provider API key must contain 1-4096 characters")
        return SecretStr(key)


class ProviderCredentialStatus(BaseModel):
    provider: str
    configured: bool
    source: str | None = None
    updated_at: str | None = None


async def _registered_org(
    org_id: str,
    session: AsyncSession,
    directory: ClerkOrganizationDirectory,
    principal: ClerkPrincipal,
) -> tuple[Organization, OrganizationMember]:
    organization = await session.scalar(
        select(Organization).where(Organization.clerk_org_id == org_id)
    )
    if organization is None:
        raise HTTPException(404, "Organization not found")
    disabled_user = await session.scalar(
        select(User.id).where(
            User.clerk_user_id == principal.user_id,
            User.disabled_at.is_not(None),
        )
    )
    if disabled_user is not None:
        raise HTTPException(403, "Account access is disabled")
    membership = await directory.membership(org_id, principal.user_id)
    if membership is None:
        raise HTTPException(404, "Organization not found")
    return organization, membership


@router.get("", response_model=list[OrganizationView])
async def joined_organizations(
    principal: ClerkPrincipal = Principal,
    session: AsyncSession = Session,
    directory: ClerkOrganizationDirectory = Directory,
) -> list[OrganizationView]:
    raise HTTPException(410, "Organization lists are managed by Clerk")
@router.post("", status_code=201, response_model=OrganizationView)
async def create_organization(
    body: CreateOrganizationBody,
    principal: ClerkPrincipal = Principal,
    session: AsyncSession = Session,
    directory: ClerkOrganizationDirectory = Directory,
) -> OrganizationView:
    """Create the user's one org and seed its starter runtime atomically."""
    if not get_settings().organization_creation_enabled:
        raise HTTPException(503, "Organization onboarding is not enabled yet")
    profile = await directory.verified_profile(principal.user_id)
    if not profile["email"]:
        raise HTTPException(403, "A verified primary email is required to create an organization")
    if not profile["first_name"] or not profile["last_name"]:
        raise HTTPException(422, "Add your first and last name to your Clerk profile first")

    await session.execute(
        pg_insert(User)
        .values(
            id=new_id(),
            clerk_user_id=principal.user_id,
            primary_verified_email=profile["email"],
            first_name=profile["first_name"],
            last_name=profile["last_name"],
        )
        .on_conflict_do_nothing(index_elements=[User.clerk_user_id])
    )
    user = await session.scalar(
        select(User).where(User.clerk_user_id == principal.user_id).with_for_update()
    )
    if user is None:
        await session.rollback()
        raise HTTPException(503, "Could not prepare the local account record")
    if user.disabled_at is not None:
        await session.rollback()
        raise HTTPException(403, "This account cannot create an organization")
    user.primary_verified_email = profile["email"]
    user.first_name = profile["first_name"]
    user.last_name = profile["last_name"]

    claim = await session.get(OrganizationCreationClaim, user.id)
    existing_owned = await session.scalar(
        select(Organization.id).where(Organization.owner_user_id == user.id)
    )
    if claim is not None or existing_owned is not None:
        await session.rollback()
        raise HTTPException(409, "Each user may own only one organization")
    if claim is None:
        claim = OrganizationCreationClaim(user_id=user.id)
        session.add(claim)
        await session.flush()

    created_clerk_org_id: str | None = None
    try:
        external = await directory.create_organization(principal.user_id, body.name)
        created_clerk_org_id = external["id"]
        organization = Organization(
            clerk_org_id=external["id"],
            name=external["name"],
            owner_user_id=user.id,
        )
        session.add(organization)
        await session.flush()
        claim.organization_id = organization.id
        session.add(
            OrganizationAudit(
                organization_id=organization.id,
                actor_user_id=user.id,
                target_user_id=user.id,
                action="organization_created",
            )
        )
        await seed_organization(session, organization.id)
        await session.commit()
    except Exception as exc:
        await session.rollback()
        if created_clerk_org_id:
            try:
                await directory.delete_organization(created_clerk_org_id)
            except Exception:
                logger.exception(
                    "Failed to compensate Clerk org creation after local provisioning failure"
                )
        if isinstance(exc, HTTPException):
            raise
        logger.exception("Organization provisioning failed")
        raise HTTPException(
            500, "Organization setup failed; no local organization was created"
        ) from exc

    return OrganizationView(
        id=organization.clerk_org_id,
        name=organization.name,
        role="org:owner",
        is_owner=True,
        registered=True,
    )


@router.post("/{org_id}/provision", status_code=201, response_model=OrganizationView)
async def provision_existing_organization(
    org_id: str,
    body: CreateOrganizationBody,
    principal: ClerkPrincipal = Principal,
    session: AsyncSession = Session,
    directory: ClerkOrganizationDirectory = Directory,
) -> OrganizationView:
    """Create the local product projection for an org created by Clerk UI."""
    if principal.org_id != org_id:
        raise HTTPException(403, "Active organization does not match the requested organization")
    if not get_settings().organization_creation_enabled:
        raise HTTPException(503, "Organization onboarding is not enabled yet")
    membership = await directory.membership(org_id, principal.user_id)
    if membership is None or membership.role not in {"org:owner", "org:admin"}:
        raise HTTPException(403, "Organization owner access required")
    if await session.scalar(select(Organization).where(Organization.clerk_org_id == org_id)):
        organization = await session.scalar(select(Organization).where(Organization.clerk_org_id == org_id))
        assert organization is not None
        return OrganizationView(
            id=organization.clerk_org_id,
            name=organization.name,
            role=membership.role,
            is_owner=membership.role == "org:owner",
            registered=True,
        )

    profile = await directory.verified_profile(principal.user_id)
    if not profile["email"]:
        raise HTTPException(403, "A verified primary email is required to create an organization")
    if not profile["first_name"] or not profile["last_name"]:
        raise HTTPException(422, "Add your first and last name to your Clerk profile first")
    await session.execute(
        pg_insert(User)
        .values(
            id=new_id(),
            clerk_user_id=principal.user_id,
            primary_verified_email=profile["email"],
            first_name=profile["first_name"],
            last_name=profile["last_name"],
        )
        .on_conflict_do_nothing(index_elements=[User.clerk_user_id])
    )
    user = await session.scalar(
        select(User).where(User.clerk_user_id == principal.user_id).with_for_update()
    )
    if user is None or user.disabled_at is not None:
        await session.rollback()
        raise HTTPException(403, "This account cannot provision an organization")
    claim = await session.get(OrganizationCreationClaim, user.id)
    existing_owned = await session.scalar(
        select(Organization.id).where(Organization.owner_user_id == user.id)
    )
    if claim is not None or existing_owned is not None:
        await session.rollback()
        raise HTTPException(409, "Each user may own only one organization")
    claim = OrganizationCreationClaim(user_id=user.id)
    session.add(claim)
    organization = Organization(clerk_org_id=org_id, name=body.name, owner_user_id=user.id)
    session.add(organization)
    await session.flush()
    claim.organization_id = organization.id
    session.add(
        OrganizationAudit(
            organization_id=organization.id,
            actor_user_id=user.id,
            target_user_id=user.id,
            action="organization_provisioned",
        )
    )
    await seed_organization(session, organization.id)
    await session.commit()
    return OrganizationView(
        id=organization.clerk_org_id,
        name=organization.name,
        role=membership.role,
        is_owner=membership.role == "org:owner",
        registered=True,
    )


async def _require_admin(
    org_id: str,
    session: AsyncSession,
    directory: ClerkOrganizationDirectory,
    principal: ClerkPrincipal,
) -> Organization:
    organization, membership = await _registered_org(org_id, session, directory, principal)
    if membership.role not in {"org:owner", "org:admin"}:
        raise HTTPException(403, "Organization admin required")
    actor_exists = await session.scalar(
        select(User.id).where(User.clerk_user_id == principal.user_id)
    )
    if actor_exists is None:
        raise HTTPException(409, "Refresh your account profile before managing organization access")
    return organization


async def _record_org_action(
    session: AsyncSession,
    organization: Organization,
    principal: ClerkPrincipal,
    action: str,
    *,
    target_clerk_user_id: str | None = None,
) -> None:
    """Persist attribution for a completed Clerk organization mutation."""
    actor_id = await session.scalar(select(User.id).where(User.clerk_user_id == principal.user_id))
    if actor_id is None:
        raise HTTPException(409, "Refresh your account profile before managing organization access")
    target_id = None
    if target_clerk_user_id:
        target_id = await session.scalar(
            select(User.id).where(User.clerk_user_id == target_clerk_user_id)
        )
    session.add(
        OrganizationAudit(
            organization_id=organization.id,
            actor_user_id=actor_id,
            target_user_id=target_id,
            action=action,
        )
    )
    try:
        await session.commit()
    except Exception as exc:
        await session.rollback()
        logger.exception("Clerk organization change succeeded but audit persistence failed")
        raise HTTPException(503, "Access changed in Clerk but audit recording failed") from exc


@router.get("/{org_id}/credentials", response_model=list[CredentialStatus])
async def provider_credential_status(
    org_id: str, principal: ClerkPrincipal = Principal, session: AsyncSession = Session,
    directory: ClerkOrganizationDirectory = Directory,
) -> list[CredentialStatus]:
    organization, _ = await _registered_org(org_id, session, directory, principal)
    bind_organization(session.sync_session, organization.id)
    rows = (await session.scalars(select(ProviderCredential).order_by(ProviderCredential.name))).all()
    return [credential_service.status(row) for row in rows]


@router.post("/{org_id}/credentials", response_model=CredentialStatus, status_code=201)
async def create_provider_credential(
    org_id: str, body: CredentialCreate, principal: ClerkPrincipal = Principal,
    session: AsyncSession = Session, directory: ClerkOrganizationDirectory = Directory,
) -> CredentialStatus:
    organization = await _require_admin(org_id, session, directory, principal)
    bind_organization(session.sync_session, organization.id)
    return credential_service.status(await credential_service.store(session, body, principal.user_id))


@router.get("/{org_id}/credentials/{credential_id}", response_model=CredentialStatus)
async def get_provider_credential(
    org_id: str, credential_id: str, principal: ClerkPrincipal = Principal,
    session: AsyncSession = Session, directory: ClerkOrganizationDirectory = Directory,
) -> CredentialStatus:
    organization, _ = await _registered_org(org_id, session, directory, principal)
    bind_organization(session.sync_session, organization.id)
    return credential_service.status(await credential_service.lookup(session, credential_id))


@router.put("/{org_id}/credentials/{credential_id}", response_model=CredentialStatus)
async def replace_provider_credential(
    org_id: str, credential_id: str, body: CredentialReplace,
    principal: ClerkPrincipal = Principal, session: AsyncSession = Session,
    directory: ClerkOrganizationDirectory = Directory,
) -> CredentialStatus:
    organization = await _require_admin(org_id, session, directory, principal)
    bind_organization(session.sync_session, organization.id)
    return credential_service.status(await credential_service.store(
        session, body, principal.user_id, credential_id=credential_id
    ))


@router.patch("/{org_id}/credentials/{credential_id}/name", response_model=CredentialStatus)
async def rename_provider_credential(
    org_id: str, credential_id: str, body: CredentialRename,
    principal: ClerkPrincipal = Principal, session: AsyncSession = Session,
    directory: ClerkOrganizationDirectory = Directory,
) -> CredentialStatus:
    organization = await _require_admin(org_id, session, directory, principal)
    bind_organization(session.sync_session, organization.id)
    return credential_service.status(await credential_service.rename(session, credential_id, body))


@router.delete("/{org_id}/credentials/{credential_id}", status_code=204)
async def delete_provider_credential(
    org_id: str, credential_id: str, body: CredentialDelete,
    principal: ClerkPrincipal = Principal, session: AsyncSession = Session,
    directory: ClerkOrganizationDirectory = Directory,
) -> None:
    organization = await _require_admin(org_id, session, directory, principal)
    bind_organization(session.sync_session, organization.id)
    await credential_service.remove(session, credential_id, body.expected_version)
