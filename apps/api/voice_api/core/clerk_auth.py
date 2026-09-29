"""Verify Clerk session tokens for user-facing endpoints."""

from dataclasses import dataclass

from clerk_backend_api import Clerk
from clerk_backend_api.security.types import AuthenticateRequestOptions
from fastapi import HTTPException, Request

from voice_api.core.config import get_settings


@dataclass(frozen=True)
class ClerkPrincipal:
    user_id: str
    org_id: str | None


async def require_clerk_user(request: Request) -> ClerkPrincipal:
    settings = get_settings()
    if not settings.clerk_secret_key:
        raise HTTPException(503, "Clerk authentication is not configured")
    authorization = request.headers.get("authorization", "")
    if not authorization.startswith("Bearer ") or not authorization[7:].strip():
        raise HTTPException(401, "Sign in required")

    parties = [
        party.strip() for party in settings.clerk_authorized_parties.split(",") if party.strip()
    ]
    if not parties:
        raise HTTPException(503, "Clerk authorized parties are not configured")

    try:
        async with Clerk(bearer_auth=settings.clerk_secret_key) as clerk:
            state = await clerk.authenticate_request_async(
                request,
                AuthenticateRequestOptions(
                    secret_key=settings.clerk_secret_key,
                    authorized_parties=parties,
                    accepts_token=["session_token"],
                ),
            )
    except Exception as exc:
        raise HTTPException(503, "Clerk verification unavailable") from exc
    if not state.is_signed_in or not state.payload:
        raise HTTPException(401, "Sign in required")
    user_id = state.payload.get("sub")
    if not isinstance(user_id, str) or not user_id:
        raise HTTPException(401, "Invalid Clerk session")
    org_claim = state.payload.get("o")
    org_id = state.payload.get("org_id") or (
        org_claim.get("id") if isinstance(org_claim, dict) else None
    )
    return ClerkPrincipal(user_id=user_id, org_id=org_id if isinstance(org_id, str) else None)
