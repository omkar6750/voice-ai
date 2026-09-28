"""Signed-in identity endpoint. Tenant grants follow in the next migration slice."""

from fastapi import APIRouter, Depends
from voice_api.core.clerk_auth import ClerkPrincipal, require_clerk_user

router = APIRouter(prefix="/auth", tags=["auth"])
Principal = Depends(require_clerk_user)


@router.get("/me")
async def me(principal: ClerkPrincipal = Principal) -> dict:
    return {"user_id": principal.user_id, "org_id": principal.org_id}
