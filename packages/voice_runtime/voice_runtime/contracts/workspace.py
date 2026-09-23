"""Singleton workspace controls; contact timezone is intentionally absent."""

from pydantic import Field

from .base import ConfigModel


class WorkspaceConfig(ConfigModel):
    recording_retention_days: int = Field(default=7, ge=1)
    pipeline_log_retention_days: int = Field(default=7, ge=1)
    pipeline_logs_enabled: bool = False
    automatic_callbacks_enabled: bool = False
    callback_due_window_minutes: int = Field(default=15, ge=1)
