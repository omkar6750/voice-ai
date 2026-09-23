from fastapi import Header, HTTPException, status

from voice_api.config import get_settings


async def require_operator(authorization: str | None = Header(default=None)) -> None:
    """Configuration endpoints are disabled until an explicit backend token exists."""
    token = get_settings().operator_token
    if not token or authorization != f"Bearer {token}":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Operator access required"
        )
