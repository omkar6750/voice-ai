from secrets import compare_digest
from typing import Any

from clerk_backend_api import Clerk
from fastapi import Depends, Header, HTTPException, status

from voice_api.core.clerk_auth import ClerkPrincipal, require_clerk_user
from voice_api.core.config import get_settings

Principal = Depends(require_clerk_user)


async def require_legacy_owner(
    principal: ClerkPrincipal = Principal,
) -> ClerkPrincipal:
    """Only the mapped Clerk owner can access unscoped legacy data."""
    settings = get_settings()
    owner_id = settings.clerk_legacy_owner_user_id
    if owner_id and compare_digest(principal.user_id, owner_id):
        return principal
    expected_email = settings.clerk_legacy_owner_email
    if owner_id or not expected_email:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Workspace access required"
        )
    try:
        async with Clerk(bearer_auth=settings.clerk_secret_key) as clerk:
            user = await clerk.users.get_async(user_id=principal.user_id)
    except Exception as exc:
        raise HTTPException(503, "Clerk identity lookup unavailable") from exc
    primary = next(
        (
            address
            for address in user.email_addresses
            if address.id == user.primary_email_address_id
        ),
        None,
    )
    verification = getattr(primary, "verification", None)
    verification_status = getattr(verification, "status", None)
    if (
        primary is None
        or primary.email_address.casefold() != expected_email.strip().casefold()
        or getattr(verification_status, "value", verification_status) != "verified"
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Workspace access required")
    return principal


async def require_runtime_service(
    runtime_token: str | None = Header(default=None, alias="X-Voice-Runtime-Token"),
) -> None:
    """Authenticate internal runtime writes without a browser/user credential."""
    expected = get_settings().runtime_service_token
    if not expected or not runtime_token or not compare_digest(runtime_token, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Runtime service access required")


def safe_evidence(data: Any) -> Any:
    """Strip authorization headers and credentials from JSON payloads before persistence."""
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
