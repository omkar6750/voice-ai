"""Typed, credential-free provider capability responses."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ProviderSlot = Literal["llm", "stt", "tts"]
ProviderStatus = Literal["configured", "unconfigured", "stale", "unavailable"]
RuntimeStatus = Literal["supported", "pending", "unavailable"]


class ProviderField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["string", "number", "boolean", "object"]
    runtime_supported: bool = True
    description: str | None = None


class ProviderVoice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    gender: str | None = None


class ProviderEntryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1)
    slots: list[ProviderSlot]
    models: list[str]
    models_by_slot: dict[ProviderSlot, list[str]]
    voices: list[ProviderVoice] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    fields: dict[str, ProviderField] = Field(default_factory=dict)
    status: ProviderStatus
    runtime_status: RuntimeStatus
    checked_at: datetime | None = None


class ProviderCatalogResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    providers: list[ProviderEntryResponse]
