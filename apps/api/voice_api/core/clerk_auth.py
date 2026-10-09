"""Verify Clerk session tokens for user-facing endpoints."""

import asyncio
from dataclasses import dataclass
from time import perf_counter

from clerk_backend_api.security.types import AuthenticateRequestOptions
from fastapi import HTTPException, Request
from voice_runtime.perf_diagnostics import measure

from voice_api.core.clerk_client import get_clerk_clients
from voice_api.core.config import get_settings
from voice_api.core.read_metrics import record


@dataclass(frozen=True)
class ClerkPrincipal:
    user_id: str
    org_id: str | None
    org_role: str | None = None
    org_permissions: tuple[str, ...] = ()


async def require_clerk_user(request: Request) -> ClerkPrincipal:
    # Only InternalDispatch can insert this ASGI object. No HTTP header/token
    # grants this identity, and all existing live membership checks still run.
    internal = request.scope.get("voice.mcp_principal")
    if isinstance(internal, ClerkPrincipal):
        return internal
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

    started = perf_counter()
    try:
        with measure("clerk", "verify"):
            clients = get_clerk_clients()
            async with asyncio.timeout(3), clients.verification_lock:
                state = await clients.sdk.authenticate_request_async(
                    request,
                    AuthenticateRequestOptions(
                        secret_key=settings.clerk_secret_key,
                        authorized_parties=parties,
                        accepts_token=["session_token"],
                    ),
                )
    except Exception as exc:
        raise HTTPException(503, "Clerk verification unavailable") from exc
    finally:
        record("token_verify", (perf_counter() - started) * 1000)
    if not state.is_signed_in or not state.payload:
        raise HTTPException(401, "Sign in required")
    user_id = state.payload.get("sub")
    if not isinstance(user_id, str) or not user_id:
        raise HTTPException(401, "Invalid Clerk session")
    org_claim = state.payload.get("o")
    org_id = state.payload.get("org_id") or (
        org_claim.get("id") if isinstance(org_claim, dict) else None
    )
    role = state.payload.get("org_role")
    permissions = state.payload.get("org_permissions")
    if isinstance(org_claim, dict):
        role = org_claim.get("rol", role)
        permissions = org_claim.get("per", permissions)
    if isinstance(role, str) and not role.startswith("org:"):
        role = f"org:{role}"
    normalized_permissions = tuple(item for item in permissions or () if isinstance(item, str))
    return ClerkPrincipal(
        user_id=user_id,
        org_id=org_id if isinstance(org_id, str) else None,
        org_role=role if isinstance(role, str) else None,
        org_permissions=normalized_permissions,
    )
