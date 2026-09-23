from fastapi import Depends

from voice_api.core.config import Settings, get_settings
from voice_api.core.security import require_operator
from voice_api.db.session import get_session

# Fast dependency aliases
get_db = get_session
SessionDep = Depends(get_session)
OperatorDep = Depends(require_operator)
SettingsDep = Depends(get_settings)

__all__ = [
    "OperatorDep",
    "SessionDep",
    "Settings",
    "SettingsDep",
    "get_db",
    "get_session",
    "get_settings",
    "require_operator",
]
