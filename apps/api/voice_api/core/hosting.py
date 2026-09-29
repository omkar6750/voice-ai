"""Fail-closed hosted capability checks, without removing local modem support."""

from fastapi import HTTPException

from voice_api.core.config import Settings, get_settings


def require_hosted_call_admission(provider: str, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    if settings.env == "dev":
        return
    if provider not in {"browser", "twilio"}:
        raise HTTPException(409, "This call transport is unavailable on the hosted service")
    if not settings.hosted_calls_enabled:
        raise HTTPException(503, "Hosted calls are disabled pending capacity acceptance")


def require_local_modem() -> None:
    if get_settings().env != "dev":
        raise HTTPException(404, "Local modem operations are unavailable on the hosted service")
