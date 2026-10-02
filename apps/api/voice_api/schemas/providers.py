"""Typed, credential-free provider capability responses."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from voice_runtime.contracts.cadence import JevQuestion

ProviderSlot = Literal["llm", "stt", "tts", "embedding"]
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


class ModelPricingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: Decimal
    completion: Decimal
    request: Decimal
    image: Decimal


class ModelOptionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    author: str | None = None
    source: str
    slots: list[ProviderSlot]
    input_modalities: list[str] = Field(default_factory=list)
    output_modalities: list[str] = Field(default_factory=list)
    modality: str | None = None
    context_length: int | None = None
    max_completion_tokens: int | None = None
    supported_parameters: list[str] = Field(default_factory=list)
    pricing: ModelPricingResponse
    is_free: bool
    tool_calling: bool = False
    structured_output: bool = False
    reasoning: bool = False
    account_available: bool = True
    runtime_supported: bool = False
    compatibility_reason: str | None = None
    endpoint_providers: list[str] = Field(default_factory=list)


class ModelCatalogResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ModelOptionResponse]
    total_count: int | None = None
    next_offset: int | None = None
    stale: bool = False
    checked_at: datetime | None = None


class OpenRouterEndpointResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_name: str | None = None
    name: str | None = None
    tag: str | None = None
    quantization: str | None = None
    context_length: int | None = None
    max_completion_tokens: int | None = None
    supported_parameters: list[str] = Field(default_factory=list)
    pricing: ModelPricingResponse
    uptime_last_30m: float | None = None
    latency_last_30m: dict[str, float] = Field(default_factory=dict)
    throughput_last_30m: dict[str, float] = Field(default_factory=dict)


class OpenRouterEndpointCatalogResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: str
    endpoints: list[OpenRouterEndpointResponse]
    checked_at: datetime | None = None


class OpenRouterAccountResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    credential_id: str
    label: str | None = None
    valid: bool
    is_free_tier: bool | None = None
    limit: float | None = None
    limit_remaining: float | None = None
    usage: float | None = None
    usage_daily: float | None = None
    usage_monthly: float | None = None
    credits_total: float | None = None
    credits_usage: float | None = None
    free_model_daily_requests: dict[str, int] = Field(default_factory=dict)
    error_category: str | None = None
    checked_at: datetime | None = None


class OpenRouterModelQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    q: str | None = Field(default=None, max_length=120)
    free_only: bool | None = None
    author: str | None = Field(default=None, max_length=120)
    tool_calling: bool | None = None
    structured_output: bool | None = None
    reasoning: bool | None = None
    min_context: int | None = Field(default=None, ge=1)
    max_prompt_price: Decimal | None = Field(default=None, ge=0)
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=25, ge=1, le=1000)


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


class LeadClassifierContract(BaseModel):
    version: int
    tool: str
    prompt: str
    questions: dict[str, JevQuestion]
    fields: dict[str, list[str]]


class ProviderCatalogResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    providers: list[ProviderEntryResponse]
    classifier_contract: LeadClassifierContract | None = None
