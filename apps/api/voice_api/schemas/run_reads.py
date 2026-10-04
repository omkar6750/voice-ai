"""Compact dashboard read contracts, separate from immutable runtime snapshots."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class RunSummaryResponse(BaseModel):
    id: str
    channel: Literal["phone", "browser"]
    transport_provider: str
    agent_version_id: str
    contact_id: str | None
    contact_name: str | None
    endpoint_id: str | None
    status: str
    created_at: datetime
    started_at: datetime | None
    ended_at: datetime | None
    call_limits: dict[str, Any] | None


class RunPageResponse(BaseModel):
    runs: list[RunSummaryResponse]
    next_cursor: str | None
    has_more: bool
