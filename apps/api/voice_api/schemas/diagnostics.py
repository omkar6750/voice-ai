"""Typed runtime diagnostic request and response contracts."""

from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue


class DiagnosticPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

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


class DiagnosticResponse(DiagnosticInput):
    run_id: str
    created_at: datetime
