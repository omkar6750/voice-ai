from fastapi import APIRouter, Depends
from voice_api.api.deps import require_legacy_owner
from voice_api.core.security import allow_organization_member
from voice_api.services.runtime_readiness import RuntimeReadiness, runtime_readiness

router = APIRouter(tags=["runtime"])


@router.get("/runtime-readiness", response_model=RuntimeReadiness)
@allow_organization_member
async def readiness(_: None = Depends(require_legacy_owner)) -> RuntimeReadiness:
    return await runtime_readiness()
