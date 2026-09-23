from secrets import compare_digest
from typing import Any

from fastapi import Header, HTTPException, status

from voice_api.core.config import get_settings


async def require_operator(authorization: str | None = Header(default=None)) -> None:
    """Configuration endpoints are disabled until an explicit backend token exists."""
    token = get_settings().operator_token
    if not token or not compare_digest((authorization or "").encode(), f"Bearer {token}".encode()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Operator access required"
        )


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
