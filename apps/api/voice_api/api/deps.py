from fastapi import Depends

from voice_api.core.config import Settings, get_settings
from voice_api.core.security import require_legacy_owner, require_runtime_service
from voice_api.db.session import get_session

# Fast dependency aliases
get_db = get_session
SessionDep = Depends(get_session)
LegacyOwnerDep = Depends(require_legacy_owner)
RuntimeServiceDep = Depends(require_runtime_service)
SettingsDep = Depends(get_settings)

__all__ = [
    "LegacyOwnerDep",
    "RuntimeServiceDep",
    "SessionDep",
    "Settings",
    "SettingsDep",
    "get_db",
    "get_session",
    "get_settings",
    "require_legacy_owner",
    "require_runtime_service",
]
