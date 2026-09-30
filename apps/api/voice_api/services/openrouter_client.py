"""Typed, redacting OpenRouter HTTP client.

The client intentionally owns the vendor response shapes. Callers consume the
small normalized models below and never inspect provider JSON directly.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator


class OpenRouterError(RuntimeError):
    def __init__(self, status_code: int, category: str, metadata_keys: tuple[str, ...] = ()):
        super().__init__(f"OpenRouter request failed: {category}")
        self.status_code = status_code
        self.category = category
        self.metadata_keys = metadata_keys


class KeyLimits(BaseModel):
    model_config = ConfigDict(extra="ignore")

    label: str | None = None
    limit: float | None = None
    limit_reset: str | None = None
    limit_remaining: float | None = None
    include_byok_in_limit: bool = False
    usage: float = 0
    usage_daily: float = 0
    usage_weekly: float = 0
    usage_monthly: float = 0
    byok_usage: float = 0
    byok_usage_daily: float = 0
    byok_usage_weekly: float = 0
    byok_usage_monthly: float = 0
    is_free_tier: bool = False
    free_model_daily_requests: dict[str, int] = Field(default_factory=dict)


class Credits(BaseModel):
    model_config = ConfigDict(extra="ignore")

    total_credits: float | None = None
    total_usage: float | None = None


class ModelPricing(BaseModel):
    model_config = ConfigDict(extra="ignore")

    prompt: Decimal = Decimal("0")
    completion: Decimal = Decimal("0")
    request: Decimal = Decimal("0")
    image: Decimal = Decimal("0")

    @field_validator("prompt", "completion", "request", "image", mode="before")
    @classmethod
    def parse_decimal(cls, value: Any) -> Decimal:
        try:
            return Decimal(str(value or "0"))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("Invalid OpenRouter pricing value") from exc


class ModelArchitecture(BaseModel):
    model_config = ConfigDict(extra="ignore")

    modality: str | None = None
    input_modalities: list[str] = Field(default_factory=list)
    output_modalities: list[str] = Field(default_factory=list)
    tokenizer: str | None = None
    instruct_type: str | None = None


class TopProvider(BaseModel):
    model_config = ConfigDict(extra="ignore")

    is_moderated: bool | None = None
    context_length: int | None = None
    max_completion_tokens: int | None = None


class OpenRouterModel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    canonical_slug: str | None = None
    name: str
    description: str | None = None
    architecture: ModelArchitecture = Field(default_factory=ModelArchitecture)
    context_length: int | None = None
    max_completion_tokens: int | None = None
    pricing: ModelPricing = Field(default_factory=ModelPricing)
    supported_parameters: list[str] = Field(default_factory=list)
    supported_voices: list[str] | None = None
    top_provider: TopProvider | None = None
    per_request_limits: dict[str, Any] | None = None

    @property
    def is_free(self) -> bool:
        return self.id.endswith(":free") or (
            self.pricing.prompt == 0 and self.pricing.completion == 0
        )


class ModelPage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    data: list[OpenRouterModel] = Field(default_factory=list)
    total_count: int | None = None
    links: dict[str, str] = Field(default_factory=dict)


class Endpoint(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str | None = None
    provider_name: str | None = None
    tag: str | None = None
    quantization: str | None = None
    context_length: int | None = None
    max_completion_tokens: int | None = None
    supported_parameters: list[str] = Field(default_factory=list)
    pricing: ModelPricing = Field(default_factory=ModelPricing)
    uptime_last_30m: float | None = None
    latency_last_30m: dict[str, float] = Field(default_factory=dict)
    throughput_last_30m: dict[str, float] = Field(default_factory=dict)


class EndpointPage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    data: dict[str, Any] = Field(default_factory=dict)

    @property
    def endpoints(self) -> list[Endpoint]:
        return [Endpoint.model_validate(item) for item in self.data.get("endpoints", [])]


class ChatUsage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost: float | None = None
    cost_details: dict[str, Any] = Field(default_factory=dict)
    is_byok: bool = False
    prompt_tokens_details: dict[str, Any] | None = None
    completion_tokens_details: dict[str, Any] | None = None

    @property
    def total_cost(self) -> float | None:
        """Provider-neutral name used by accounting consumers."""
        return self.cost


class ChatChoice(BaseModel):
    model_config = ConfigDict(extra="ignore")

    message: dict[str, Any] = Field(default_factory=dict)
    finish_reason: str | None = None


class ChatCompletion(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    model: str
    choices: list[ChatChoice] = Field(default_factory=list)
    usage: ChatUsage | None = None
    openrouter_metadata: dict[str, Any] | None = None


class Generation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    model: str | None = None
    provider_name: str | None = None
    is_byok: bool = False
    total_cost: float | None = None
    upstream_inference_cost: float | None = None
    tokens_prompt: int | None = None
    tokens_completion: int | None = None
    native_tokens_reasoning: int | None = None
    latency: float | None = None
    generation_time: float | None = None
    finish_reason: str | None = None


class OpenRouterClient:
    def __init__(self, api_key: str, *, base_url: str = "https://openrouter.ai/api/v1") -> None:
        self._headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
        self._base_url = base_url.rstrip("/")

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.request(
                    method, f"{self._base_url}{path}", headers=self._headers, **kwargs
                )
        except httpx.HTTPError as exc:
            raise OpenRouterError(0, "transport_error") from exc
        if response.is_error:
            category = {
                400: "invalid_request",
                401: "invalid_key",
                402: "insufficient_credits",
                403: "forbidden",
                404: "not_found",
                408: "timeout",
                429: "rate_limited",
            }.get(response.status_code, "http_error")
            metadata_keys: tuple[str, ...] = ()
            try:
                body = response.json()
                error = body.get("error", {}) if isinstance(body, dict) else {}
                code = str(error.get("code") or "").casefold()
                if "quota" in code or "limit" in code:
                    category = "quota_exceeded"
                elif "credit" in code or "balance" in code:
                    category = "insufficient_credits"
                elif "model" in code and response.status_code == 404:
                    category = "model_unavailable"
                metadata = error.get("metadata")
                if isinstance(metadata, dict):
                    metadata_keys = tuple(sorted(str(key) for key in metadata))
            except (ValueError, TypeError):
                pass
            raise OpenRouterError(response.status_code, category, metadata_keys)
        try:
            return response.json()
        except ValueError as exc:
            raise OpenRouterError(response.status_code, "invalid_json") from exc

    async def key(self) -> KeyLimits:
        return KeyLimits.model_validate((await self._request("GET", "/key")).get("data", {}))

    async def credits(self) -> Credits:
        return Credits.model_validate(
            (await self._request("GET", "/credits")).get("data", {})
        )

    async def models(self, *, user: bool = True, **params: Any) -> ModelPage:
        path = "/models/user" if user else "/models"
        return ModelPage.model_validate(await self._request("GET", path, params=params))

    async def endpoints(self, author: str, slug: str) -> EndpointPage:
        return EndpointPage.model_validate(
            await self._request("GET", f"/models/{author}/{slug}/endpoints")
        )

    async def chat(self, *, model: str, messages: list[dict[str, Any]], **params: Any) -> ChatCompletion:
        body = {"model": model, "messages": messages, "stream": False, **params}
        return ChatCompletion.model_validate(
            await self._request("POST", "/chat/completions", json=body)
        )

    async def generation(self, generation_id: str) -> Generation:
        payload = await self._request("GET", "/generation", params={"id": generation_id})
        return Generation.model_validate(payload.get("data", {}))
