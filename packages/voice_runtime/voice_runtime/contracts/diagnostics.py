"""Typed runtime diagnostic payloads shared by workers and the API boundary."""

from datetime import datetime
from typing import Literal
from uuid import uuid4

from pydantic import AwareDatetime, Field, JsonValue

from .base import ConfigModel


class DiagnosticPayload(ConfigModel):
    severity: Literal["info", "warning", "error"]
    category: str = Field(min_length=1, max_length=80)
    source: Literal["provider", "modem", "transport", "call", "evidence", "runtime"]
    code: str | None = Field(default=None, max_length=120)
    message: str = Field(min_length=1, max_length=500)
    detail: str | None = Field(default=None, max_length=2000)
    retryable: bool = False
    uncertain: bool = False
    provider_request_id: str | None = Field(default=None, max_length=255)
    http_status: int | None = Field(default=None, ge=100, le=599)
    retry_after_seconds: float | None = Field(default=None, ge=0, le=86400)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class DiagnosticInput(DiagnosticPayload):
    diagnostic_id: str = Field(min_length=1, max_length=36)
    occurred_at: AwareDatetime


def diagnostic_dict(
    *,
    severity: Literal["info", "warning", "error"],
    category: str,
    source: Literal["provider", "modem", "transport", "call", "evidence", "runtime"],
    message: str,
    code: str | None = None,
    detail: str | None = None,
    retryable: bool = False,
    uncertain: bool = False,
    provider_request_id: str | None = None,
    http_status: int | None = None,
    retry_after_seconds: float | None = None,
    metadata: dict[str, JsonValue] | None = None,
) -> dict:
    """Build a progress-compatible diagnostic without exposing raw provider bodies."""
    return DiagnosticInput(
        diagnostic_id=uuid4().hex,
        occurred_at=datetime.now().astimezone(),
        severity=severity,
        category=category,
        source=source,
        code=code,
        message=message,
        detail=detail,
        retryable=retryable,
        uncertain=uncertain,
        provider_request_id=provider_request_id,
        http_status=http_status,
        retry_after_seconds=retry_after_seconds,
        metadata=metadata or {},
    ).model_dump(mode="json")
