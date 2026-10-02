"""Typed API contracts for tool capabilities and configuration validation."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field
from voice_runtime.contracts import RegisteredHandlerSpec, ToolConfig


class ToolSummaryResponse(BaseModel):
    id: str
    name: str


class ToolListResponse(BaseModel):
    tools: list[ToolSummaryResponse]


class ToolCatalogSummary(ToolSummaryResponse):
    latest_published_version: int | None
    draft_count: int


class ToolCatalogResponse(BaseModel):
    tools: list[ToolCatalogSummary]


class ToolVersionSummary(BaseModel):
    id: str
    tool_id: str
    version: int
    revision: int
    status: Literal["draft", "published"]
    created_at: datetime
    published_at: datetime | None
    parent_id: str | None
    parent_version: int | None


class ToolVersionPage(BaseModel):
    tool_id: str
    tool_name: str
    versions: list[ToolVersionSummary]
    has_more: bool
    next_before_version: int | None


class ToolUsageRow(BaseModel):
    agent_id: str
    agent_name: str
    agent_version_id: str
    agent_version: int
    agent_status: str
    binding_key: str
    tool_id: str
    tool_version_id: str
    tool_version: int


class ToolUsagePage(BaseModel):
    bindings: list[ToolUsageRow]
    has_more: bool


class ToolVersionResponse(BaseModel):
    id: str
    version: int
    revision: int
    status: Literal["draft", "published"]
    config: ToolConfig


class ToolVersionsResponse(BaseModel):
    versions: list[ToolVersionResponse]


class ToolCreateBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    config: ToolConfig


class ToolRevisionBody(BaseModel):
    revision: int = Field(gt=0)
    config: ToolConfig
    note: str | None = None


class ToolCreateResponse(BaseModel):
    tool_id: str
    version_id: str


class ToolVersionMutationResponse(BaseModel):
    id: str
    revision: int | None = None
    status: Literal["draft", "published"] | None = None
    config: ToolConfig | None = None


class ToolValidationResponse(BaseModel):
    id: str
    valid: bool
    revision: int
    config: ToolConfig | None = None
    issues: list[ToolValidationIssue] = Field(default_factory=list)


class ToolImpactAgent(BaseModel):
    agent_id: str
    agent_name: str
    version: int
    status: str


class ToolImpactResponse(BaseModel):
    tool_id: str
    tool_name: str
    is_system_tool: bool
    can_delete: bool
    system_tool_reason: str | None = None
    bound_agents: list[ToolImpactAgent] = Field(default_factory=list)
    versions_count: int


class HTTPRetryPolicy(BaseModel):
    max_attempts: int = Field(ge=1, le=5)
    backoff_secs_min: float = Field(ge=0)
    write_idempotency_required: bool


class HTTPToolPolicy(BaseModel):
    allowed_methods: list[str]
    allowed_schemes: list[str]
    credentials_policy: str
    retry_policy: HTTPRetryPolicy
    timeout_secs: dict[str, float]
    follow_redirects: Literal[False] = False


class ToolHandlerCatalog(BaseModel):
    handlers: list[RegisteredHandlerSpec]
    http_policy: HTTPToolPolicy


class ToolValidationIssue(BaseModel):
    severity: Literal["error", "warning"]
    code: str
    scope: str
    record_id: str | None = None
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolValidationReport(BaseModel):
    generated_at: datetime
    valid: bool
    handlers: list[RegisteredHandlerSpec]
    issues: list[ToolValidationIssue] = Field(default_factory=list)
    cleanup_candidates: list[str] = Field(default_factory=list)
    cleaned_record_ids: list[str] = Field(default_factory=list)


class ToolCleanupRequest(BaseModel):
    apply: bool = False
