"""Typed request and response contracts for workspace settings."""

from pydantic import BaseModel, Field
from voice_runtime.contracts import WorkspaceConfig


class WorkspaceUpdateRequest(BaseModel):
    revision: int = Field(gt=0)
    config: WorkspaceConfig


class WorkspaceResponse(BaseModel):
    revision: int
    config: WorkspaceConfig
