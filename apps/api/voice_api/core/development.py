"""Explicit boundary for destructive development-only configuration cleanup."""

from fastapi import HTTPException

from voice_api.core.config import get_settings


def require_development_cleanup() -> None:
    """Never disable ownership/immutable-version triggers in a hosted environment."""
    if get_settings().env != "dev":
        raise HTTPException(403, "Hard configuration deletion is available only in development")
