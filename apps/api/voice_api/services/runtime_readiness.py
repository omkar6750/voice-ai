"""Bounded, read-only runtime admission probe. Never modifies assignments."""

from typing import Literal

import httpx
from fastapi import HTTPException
from pydantic import BaseModel

from voice_api.services.runtime_dispatch import client


class RuntimeReadiness(BaseModel):
    state: Literal["starting", "ready", "busy", "unavailable"]
    retry_after_seconds: int = 3
    code: str | None = None


async def runtime_readiness() -> RuntimeReadiness:
    try:
        runtime = client()
        health = await runtime.get("/health", timeout=2)
        if health.status_code in {502, 503, 504}:
            return RuntimeReadiness(state="starting")
        if health.status_code != 200:
            return RuntimeReadiness(state="unavailable", code="runtime_health_failed")
        status = await runtime.get("/v1/status", timeout=2)
        if status.status_code in {502, 503, 504}:
            return RuntimeReadiness(state="starting")
        if status.status_code in {401, 403}:
            return RuntimeReadiness(state="unavailable", code="runtime_authentication_failed")
        if status.status_code != 200:
            return RuntimeReadiness(state="unavailable", code="runtime_status_failed")
        data = status.json()
        if not isinstance(data, dict) or not data.get("boot_id"):
            return RuntimeReadiness(state="unavailable", code="runtime_status_invalid")
        if data.get("admission_enabled") is False:
            return RuntimeReadiness(state="unavailable", code="runtime_admission_disabled")
        if data.get("blocked") or data.get("draining") or data.get("admission_available") is False:
            return RuntimeReadiness(state="busy", code="runtime_busy")
        return RuntimeReadiness(state="ready")
    except (httpx.HTTPError, TimeoutError):
        return RuntimeReadiness(state="starting")
    except (HTTPException, ValueError):
        return RuntimeReadiness(state="unavailable", code="runtime_configuration_invalid")


async def require_runtime_ready() -> None:
    result = await runtime_readiness()
    if result.state != "ready":
        raise HTTPException(
            503,
            {
                "code": result.code or "runtime_starting",
                "message": "Voice runtime is not ready. Wait for readiness before starting a new session.",
            },
        )
