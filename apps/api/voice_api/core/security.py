from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
from secrets import compare_digest
from typing import Any

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from voice_api.core.clerk_auth import ClerkPrincipal, require_clerk_user
from voice_api.core.clerk_organizations import (
    ClerkOrganizationDirectory,
    get_clerk_organization_directory,
)
from voice_api.core.config import get_settings
from voice_api.db.session import get_session
from voice_api.db.tenant_scope import bind_organization, mark_platform_admin
from voice_api.models import (
    LegacyDataTenant,
    Organization,
    PlatformAdministrator,
    PlatformSupportSession,
    User,
)

Principal = Depends(require_clerk_user)
Session = Depends(get_session)
Directory = Depends(get_clerk_organization_directory)


def allow_organization_member(endpoint: Callable) -> Callable:
    """Explicitly mark a route as safe for Clerk organization members."""
    endpoint.__allow_organization_member__ = True
    return endpoint


async def require_organization_access(
    request: Request,
    principal: ClerkPrincipal = Principal,
    session: AsyncSession = Session,
    directory: ClerkOrganizationDirectory = Directory,
) -> ClerkPrincipal:
    """Verify live Clerk membership and bind the registered active org to DB scope."""
    support_token = request.headers.get("x-platform-support-session")
    if support_token:
        if len(support_token) > 256:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Platform support session invalid")
        token_hash = sha256(support_token.encode("utf-8")).hexdigest()
        user_id = await session.scalar(
            select(User.id).where(
                User.clerk_user_id == principal.user_id,
                User.disabled_at.is_(None),
            )
        )
        assignment = (
            await session.scalar(
                select(PlatformAdministrator.id).where(PlatformAdministrator.user_id == user_id)
            )
            if user_id
            else None
        )
        support_session = await session.get(PlatformSupportSession, token_hash)
        if (
            not user_id
            or not assignment
            or support_session is None
            or support_session.user_id != user_id
            or support_session.revoked_at is not None
            or support_session.expires_at <= datetime.now(UTC)
        ):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Platform support session invalid")
        organization = await session.get(Organization, support_session.organization_id)
        if organization is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found")
        request.state.platform_support_session = token_hash
        bind_organization(session.sync_session, organization.id)
        return ClerkPrincipal(
            user_id=principal.user_id, org_id=organization.clerk_org_id, org_role="org:admin"
        )
    if not principal.org_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Organization access required")
    try:
        organization_id = await session.scalar(
            select(Organization.id).where(Organization.clerk_org_id == principal.org_id)
        )
    except SQLAlchemyError as exc:
        raise HTTPException(503, "Organization access unavailable") from exc
    if organization_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Organization access required")
    if (
        hasattr(session, "in_transaction")
        and session.in_transaction()
        and not session.new
        and not session.dirty
        and not session.deleted
    ):
        await session.rollback()
    membership = await directory.membership(principal.org_id, principal.user_id)
    if membership is None or membership.role not in {"org:owner", "org:admin", "org:member"}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Organization access required")
    disabled_user = await session.scalar(
        select(User.id).where(
            User.clerk_user_id == principal.user_id,
            User.disabled_at.is_not(None),
        )
    )
    if disabled_user is not None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account access is disabled")
    if membership.role == "org:member":
        route = request.scope.get("route")
        endpoint = getattr(route, "endpoint", None)
        if not getattr(endpoint, "__allow_organization_member__", False):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Organization admin required")
    bind_organization(session.sync_session, organization_id)
    return ClerkPrincipal(
        user_id=principal.user_id,
        org_id=principal.org_id,
        org_role="org:admin" if membership.role == "org:owner" else membership.role,
    )


async def require_platform_admin_user(
    principal: ClerkPrincipal,
    session: AsyncSession,
) -> User:
    """Resolve the database-backed platform administrator assignment."""
    user = await session.scalar(
        select(User).where(
            User.clerk_user_id == principal.user_id,
            User.disabled_at.is_(None),
        )
    )
    assignment = (
        await session.scalar(
            select(PlatformAdministrator.id).where(PlatformAdministrator.user_id == user.id)
        )
        if user
        else None
    )
    if user is None or assignment is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Platform administrator required")
    sync_session = getattr(session, "sync_session", None)
    if sync_session is not None:
        mark_platform_admin(sync_session)
    return user


async def require_platform_admin(
    principal: ClerkPrincipal = Principal,
    session: AsyncSession = Session,
) -> ClerkPrincipal:
    """Authorize platform-only operations independently of the active org."""
    await require_platform_admin_user(principal, session)
    return principal


async def require_legacy_data_access(
    request: Request,
    principal: ClerkPrincipal = Principal,
    session: AsyncSession = Session,
    directory: ClerkOrganizationDirectory = Directory,
) -> ClerkPrincipal:
    """Restrict legacy-only operations to members of the migrated Original org."""
    principal = await require_organization_access(request, principal, session, directory)
    try:
        legacy_org_id = await session.scalar(select(LegacyDataTenant.organization_id))
    except SQLAlchemyError as exc:
        raise HTTPException(503, "Legacy organization access unavailable") from exc
    if not legacy_org_id or session.sync_session.info.get("organization_scope_id") != legacy_org_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Legacy organization access required")
    return principal


# Kept as an import alias for route modules during the RBAC dependency rename.
require_legacy_owner = require_organization_access


def runtime_token_for_run(secret: str, run_id: str) -> str:
    """Derive a non-transferable runtime credential for one run."""
    return f"{run_id}.{sha256(f'{secret}:{run_id}'.encode()).hexdigest()}"


async def require_runtime_service(
    runtime_token: str | None = Header(default=None, alias="X-Voice-Runtime-Token"),
    run_id: str | None = None,
) -> None:
    """Authenticate runtime writes, scoping run mutations to the addressed run."""
    expected = get_settings().runtime_service_token
    if run_id is not None and expected:
        expected = runtime_token_for_run(expected, run_id)
    if not expected or not runtime_token or not compare_digest(runtime_token, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Runtime service access required")


def safe_evidence(data: Any) -> Any:
    """Strip authorization headers and credentials from JSON payloads before persistence."""
    from voice_shared.dev_visibility import is_development, redact_api_keys

    if is_development():
        return redact_api_keys(data)
    if isinstance(data, dict):
        return {
            k: "[REDACTED]"
            if k.lower() in ("authorization", "bearer", "api_key", "secret", "token", "password")
            else safe_evidence(v)
            for k, v in data.items()
        }
    if isinstance(data, list):
        return [safe_evidence(v) for v in data]
    return data
