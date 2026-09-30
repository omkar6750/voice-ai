"""Member-scoped Clerk organization directory and standard invitations."""

import re

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from pydantic import BaseModel, SecretStr, field_validator
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
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
from voice_api.schemas.providers import (
    ModelCatalogResponse,
    OpenRouterAccountResponse,
    OpenRouterEndpointCatalogResponse,
    OpenRouterEndpointResponse,
    OpenRouterModelQuery,
)
from voice_api.services import credential_service
from voice_api.services.credential_service import credential_scope
from voice_api.services.openrouter_catalog import account_status, model_catalog
from voice_api.services.openrouter_client import OpenRouterClient, OpenRouterError
from voice_api.services.organization_seed import seed_organization
from voice_api.services.provider_credentials import decrypt_provider_key
from voice_api.services.vault_service import VaultError

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


class MemberView(BaseModel):
    user_id: str
    role: str
    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    is_owner: bool = False


class InvitationView(BaseModel):
    id: str
    email_address: str
    role: str
    status: str


class InviteBody(BaseModel):
    email_address: str
    role: str = "org:member"

    @field_validator("email_address")
    @classmethod
    def validate_email(cls, value: str) -> str:
        email = value.strip().casefold()
        if len(email) > 320 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            raise ValueError("Valid email address required")
        return email

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        if value not in {"org:member", "org:admin"}:
            raise ValueError("Only standard Clerk organization roles are supported")
        return value


class RoleBody(BaseModel):
    role: str

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        if value not in {"org:member", "org:admin"}:
            raise ValueError("Only standard Clerk organization roles are supported")
        return value


class OwnershipTransferBody(BaseModel):
    user_id: str


class OwnershipTransferView(BaseModel):
    organization_id: str
    owner_user_id: str


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
    memberships = await directory.joined(principal.user_id)
    if not memberships:
        return []
    ids = [item.clerk_org_id for item in memberships]
    local_rows = (
        await session.scalars(select(Organization).where(Organization.clerk_org_id.in_(ids)))
    ).all()
    local = {row.clerk_org_id: row for row in local_rows}
    user = await session.scalar(select(User).where(User.clerk_user_id == principal.user_id))
    return [
        OrganizationView(
            id=item.clerk_org_id,
            name=item.name,
            role=item.role,
            is_owner=bool(
                user
                and item.clerk_org_id in local
                and local[item.clerk_org_id].owner_user_id == user.id
            ),
            registered=item.clerk_org_id in local,
        )
        for item in memberships
    ]


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
        role="org:admin",
        is_owner=True,
        registered=True,
    )


@router.get("/{org_id}", response_model=OrganizationView)
async def organization_detail(
    org_id: str,
    principal: ClerkPrincipal = Principal,
    session: AsyncSession = Session,
    directory: ClerkOrganizationDirectory = Directory,
) -> OrganizationView:
    organization, membership = await _registered_org(org_id, session, directory, principal)
    user = await session.scalar(select(User).where(User.clerk_user_id == principal.user_id))
    return OrganizationView(
        id=org_id,
        name=organization.name,
        role=membership.role,
        is_owner=bool(user and organization.owner_user_id == user.id),
        registered=True,
    )


@router.get("/{org_id}/members", response_model=list[MemberView])
async def organization_members(
    org_id: str,
    principal: ClerkPrincipal = Principal,
    session: AsyncSession = Session,
    directory: ClerkOrganizationDirectory = Directory,
) -> list[MemberView]:
    organization, _ = await _registered_org(org_id, session, directory, principal)
    members = await directory.members(org_id)
    clerk_ids = [member.user_id for member in members]
    users = (
        (await session.scalars(select(User).where(User.clerk_user_id.in_(clerk_ids)))).all()
        if clerk_ids
        else []
    )
    local = {user.clerk_user_id: user for user in users}
    return [
        MemberView(
            user_id=member.user_id,
            role=member.role,
            email=member.email,
            first_name=member.first_name,
            last_name=member.last_name,
            is_owner=bool(
                member.user_id in local and local[member.user_id].id == organization.owner_user_id
            ),
        )
        for member in members
    ]


async def _require_admin(
    org_id: str,
    session: AsyncSession,
    directory: ClerkOrganizationDirectory,
    principal: ClerkPrincipal,
) -> Organization:
    organization, membership = await _registered_org(org_id, session, directory, principal)
    if membership.role != "org:admin":
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


@router.get("/{org_id}/invitations", response_model=list[InvitationView])
async def organization_invitations(
    org_id: str,
    principal: ClerkPrincipal = Principal,
    session: AsyncSession = Session,
    directory: ClerkOrganizationDirectory = Directory,
) -> list[InvitationView]:
    await _require_admin(org_id, session, directory, principal)
    return [InvitationView.model_validate(item) for item in await directory.invitations(org_id)]


@router.get("/{org_id}/credentials", response_model=list[CredentialStatus])
async def provider_credential_status(
    org_id: str, principal: ClerkPrincipal = Principal, session: AsyncSession = Session,
    directory: ClerkOrganizationDirectory = Directory,
) -> list[CredentialStatus]:
    organization, _ = await _registered_org(org_id, session, directory, principal)
    bind_organization(session.sync_session, organization.id)
    rows = (await session.scalars(select(ProviderCredential).order_by(ProviderCredential.name))).all()
    return [credential_service.status(row) for row in rows]


async def _openrouter_client(
    org_id: str,
    credential_id: str,
    principal: ClerkPrincipal,
    session: AsyncSession,
    directory: ClerkOrganizationDirectory,
) -> tuple[Organization, OpenRouterClient]:
    organization, _ = await _registered_org(org_id, session, directory, principal)
    bind_organization(session.sync_session, organization.id)
    row = await credential_service.lookup(session, credential_id)
    if row.provider != "openrouter" or row.status != "stored":
        raise HTTPException(422, "Credential is not an active OpenRouter credential")
    try:
        key = decrypt_provider_key(
            row.provider, row.ciphertext, row.key_id, scope=credential_scope(row)
        )
    except VaultError as error:
        raise HTTPException(503, "OpenRouter credential is unavailable") from error
    return organization, OpenRouterClient(key)


def _openrouter_http_error(error: OpenRouterError) -> HTTPException:
    status = error.status_code if 400 <= error.status_code < 500 else 502
    return HTTPException(
        status,
        detail={"category": error.category, "metadata_keys": list(error.metadata_keys)},
    )


@router.get("/{org_id}/openrouter/{credential_id}/account", response_model=OpenRouterAccountResponse)
async def openrouter_account(
    org_id: str,
    credential_id: str,
    principal: ClerkPrincipal = Principal,
    session: AsyncSession = Session,
    directory: ClerkOrganizationDirectory = Directory,
) -> OpenRouterAccountResponse:
    _, client = await _openrouter_client(org_id, credential_id, principal, session, directory)
    return await account_status(client, credential_id)


@router.get("/{org_id}/openrouter/{credential_id}/models", response_model=ModelCatalogResponse)
async def openrouter_models(
    org_id: str,
    credential_id: str,
    q: str | None = Query(default=None, max_length=120),
    free_only: bool | None = None,
    author: str | None = Query(default=None, max_length=120),
    tool_calling: bool | None = None,
    structured_output: bool | None = None,
    reasoning: bool | None = None,
    min_context: int | None = Query(default=None, ge=1),
    max_prompt_price: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
    principal: ClerkPrincipal = Principal,
    session: AsyncSession = Session,
    directory: ClerkOrganizationDirectory = Directory,
) -> ModelCatalogResponse:
    from decimal import Decimal, InvalidOperation

    try:
        price = Decimal(max_prompt_price) if max_prompt_price is not None else None
    except InvalidOperation as error:
        raise HTTPException(422, "max_prompt_price must be a decimal") from error
    _, client = await _openrouter_client(org_id, credential_id, principal, session, directory)
    try:
        return await model_catalog(client, OpenRouterModelQuery(
            q=q, free_only=free_only, author=author, tool_calling=tool_calling,
            structured_output=structured_output, reasoning=reasoning, min_context=min_context,
            max_prompt_price=price, offset=offset, limit=limit,
        ))
    except OpenRouterError as error:
        raise _openrouter_http_error(error) from error


@router.get(
    "/{org_id}/openrouter/{credential_id}/models/{author}/{slug}/endpoints",
    response_model=OpenRouterEndpointCatalogResponse,
)
async def openrouter_model_endpoints(
    org_id: str,
    credential_id: str,
    author: str,
    slug: str,
    principal: ClerkPrincipal = Principal,
    session: AsyncSession = Session,
    directory: ClerkOrganizationDirectory = Directory,
) -> OpenRouterEndpointCatalogResponse:
    from datetime import UTC, datetime

    _, client = await _openrouter_client(org_id, credential_id, principal, session, directory)
    try:
        page = await client.endpoints(author, slug)
    except OpenRouterError as error:
        raise _openrouter_http_error(error) from error
    return OpenRouterEndpointCatalogResponse(
        model_id=page.data.get("id", f"{author}/{slug}"),
        endpoints=[OpenRouterEndpointResponse.model_validate(endpoint.model_dump()) for endpoint in page.endpoints],
        checked_at=datetime.now(UTC),
    )


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


@router.post("/{org_id}/invitations", status_code=201, response_model=InvitationView)
async def send_invitation(
    org_id: str,
    body: InviteBody,
    principal: ClerkPrincipal = Principal,
    session: AsyncSession = Session,
    directory: ClerkOrganizationDirectory = Directory,
) -> InvitationView:
    organization = await _require_admin(org_id, session, directory, principal)
    result = await directory.invite(org_id, principal.user_id, body.email_address, body.role)
    try:
        await _record_org_action(session, organization, principal, "invitation_created")
    except HTTPException as audit_error:
        try:
            await directory.revoke(org_id, result["id"], principal.user_id)
        except Exception as compensation_error:
            logger.exception("Could not revoke Clerk invitation after audit persistence failure")
            raise HTTPException(
                503,
                "Invitation was created but audit failed and invitation rollback failed; manual reconciliation is required",
            ) from compensation_error
        raise audit_error
    return InvitationView.model_validate(result)


@router.delete("/{org_id}/invitations/{invitation_id}", status_code=204)
async def revoke_invitation(
    org_id: str,
    invitation_id: str,
    principal: ClerkPrincipal = Principal,
    session: AsyncSession = Session,
    directory: ClerkOrganizationDirectory = Directory,
) -> None:
    organization = await _require_admin(org_id, session, directory, principal)
    await directory.revoke(org_id, invitation_id, principal.user_id)
    await _record_org_action(session, organization, principal, "invitation_revoked")


async def _guard_member_change(
    org_id: str,
    user_id: str,
    principal: ClerkPrincipal,
    session: AsyncSession,
    directory: ClerkOrganizationDirectory,
    *,
    removing_admin: bool,
) -> tuple[Organization, OrganizationMember]:
    organization = await _require_admin(org_id, session, directory, principal)
    target = await directory.membership(org_id, user_id)
    if target is None:
        raise HTTPException(404, "Member not found")
    local_id = await session.scalar(select(User.id).where(User.clerk_user_id == user_id))
    if local_id == organization.owner_user_id:
        raise HTTPException(409, "Transfer ownership before changing the owner")
    if removing_admin and target.role == "org:admin":
        members = await directory.members(org_id)
        if sum(member.role == "org:admin" for member in members) <= 1:
            raise HTTPException(409, "The final organization admin cannot be removed")
    return organization, target


@router.patch("/{org_id}/members/{user_id}", status_code=204)
async def update_member_role(
    org_id: str,
    user_id: str,
    body: RoleBody,
    principal: ClerkPrincipal = Principal,
    session: AsyncSession = Session,
    directory: ClerkOrganizationDirectory = Directory,
) -> None:
    organization, target = await _guard_member_change(
        org_id,
        user_id,
        principal,
        session,
        directory,
        removing_admin=body.role == "org:member",
    )
    await directory.change_role(org_id, user_id, body.role)
    action = "member_promoted_to_admin" if body.role == "org:admin" else "member_changed_to_member"
    try:
        await _record_org_action(
            session, organization, principal, action, target_clerk_user_id=user_id
        )
    except HTTPException as audit_error:
        if target.role != body.role:
            try:
                await directory.change_role(org_id, user_id, target.role)
            except Exception as compensation_error:
                logger.exception("Could not restore Clerk role after audit persistence failure")
                raise HTTPException(
                    503,
                    "Member role changed but audit failed and role rollback failed; manual reconciliation is required",
                ) from compensation_error
        raise audit_error


@router.delete("/{org_id}/members/{user_id}", status_code=204)
async def remove_organization_member(
    org_id: str,
    user_id: str,
    principal: ClerkPrincipal = Principal,
    session: AsyncSession = Session,
    directory: ClerkOrganizationDirectory = Directory,
) -> None:
    organization, _target = await _guard_member_change(
        org_id, user_id, principal, session, directory, removing_admin=True
    )
    await directory.remove_member(org_id, user_id)
    await _record_org_action(
        session, organization, principal, "member_removed", target_clerk_user_id=user_id
    )


@router.post("/{org_id}/ownership-transfer", response_model=OwnershipTransferView)
async def transfer_ownership(
    org_id: str,
    body: OwnershipTransferBody,
    principal: ClerkPrincipal = Principal,
    session: AsyncSession = Session,
    directory: ClerkOrganizationDirectory = Directory,
) -> OwnershipTransferView:
    """Transfer local ownership only after verifying both live Clerk memberships."""
    organization = await session.scalar(
        select(Organization).where(Organization.clerk_org_id == org_id).with_for_update()
    )
    if organization is None:
        raise HTTPException(404, "Organization not found")
    actor = await session.scalar(select(User).where(User.clerk_user_id == principal.user_id))
    if actor is None or actor.id != organization.owner_user_id:
        raise HTTPException(403, "Only the organization owner may transfer ownership")
    actor_membership = await directory.membership(org_id, principal.user_id)
    if actor_membership is None or actor_membership.role != "org:admin":
        raise HTTPException(403, "Current owner must be an organization admin")
    if body.user_id == principal.user_id:
        raise HTTPException(422, "Select another member")
    target_membership = await directory.membership(org_id, body.user_id)
    if target_membership is None:
        raise HTTPException(404, "Target member not found")
    target = await session.scalar(select(User).where(User.clerk_user_id == body.user_id))
    if target is not None:
        existing = await session.scalar(
            select(Organization.id).where(Organization.owner_user_id == target.id)
        )
        if existing is not None:
            raise HTTPException(409, "Target already owns an organization")
    else:
        target = User(
            clerk_user_id=body.user_id,
            primary_verified_email=target_membership.email,
            first_name=target_membership.first_name,
            last_name=target_membership.last_name,
        )
        session.add(target)
        await session.flush()
    actor_claim = await session.get(OrganizationCreationClaim, actor.id, with_for_update=True)
    if actor_claim is not None and actor_claim.organization_id == organization.id:
        actor_claim.organization_id = None
        await session.flush()
    target_claim = await session.get(OrganizationCreationClaim, target.id, with_for_update=True)
    if target_claim is not None and target_claim.organization_id != organization.id:
        raise HTTPException(409, "Target has already owned another organization")
    if target_claim is None:
        session.add(OrganizationCreationClaim(user_id=target.id, organization_id=organization.id))
    promoted = False
    if target_membership.role != "org:admin":
        await directory.change_role(org_id, body.user_id, "org:admin")
        promoted = True
    organization.owner_user_id = target.id
    session.add(
        OrganizationAudit(
            organization_id=organization.id,
            actor_user_id=actor.id,
            target_user_id=target.id,
            action="ownership_transferred",
        )
    )
    try:
        await session.commit()
    except Exception as exc:
        await session.rollback()
        if promoted:
            try:
                await directory.change_role(org_id, body.user_id, "org:member")
            except Exception as compensation_error:
                logger.exception("Could not restore Clerk role after failed ownership transfer")
                raise HTTPException(
                    503,
                    "Ownership transfer failed and Clerk role rollback failed; manual reconciliation is required",
                ) from compensation_error
        if isinstance(exc, IntegrityError):
            raise HTTPException(
                409, "Ownership transfer conflicted; the target's previous role was restored"
            ) from exc
        logger.exception("Ownership transfer database commit failed")
        raise HTTPException(
            503, "Ownership transfer failed; the target's previous role was restored"
        ) from exc
    return OwnershipTransferView(organization_id=org_id, owner_user_id=body.user_id)
