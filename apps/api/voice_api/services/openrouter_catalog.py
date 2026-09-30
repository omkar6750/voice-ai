"""Normalize OpenRouter's account-specific model catalog for dashboard use."""

from __future__ import annotations

from datetime import UTC, datetime

from voice_api.schemas.providers import (
    ModelCatalogResponse,
    ModelOptionResponse,
    ModelPricingResponse,
    OpenRouterAccountResponse,
    OpenRouterModelQuery,
)
from voice_api.services.openrouter_client import OpenRouterClient, OpenRouterError, OpenRouterModel


def _author(model_id: str) -> str | None:
    return model_id.split("/", 1)[0] if "/" in model_id else None


def _option(model: OpenRouterModel) -> ModelOptionResponse:
    params = set(model.supported_parameters)
    text_output = not model.architecture.output_modalities or "text" in model.architecture.output_modalities
    return ModelOptionResponse(
        id=model.id,
        name=model.name,
        author=_author(model.id),
        source="openrouter",
        slots=["llm"] if text_output else [],
        input_modalities=model.architecture.input_modalities,
        output_modalities=model.architecture.output_modalities,
        modality=model.architecture.modality,
        context_length=model.context_length,
        max_completion_tokens=model.max_completion_tokens,
        supported_parameters=model.supported_parameters,
        pricing=ModelPricingResponse(
            prompt=model.pricing.prompt,
            completion=model.pricing.completion,
            request=model.pricing.request,
            image=model.pricing.image,
        ),
        is_free=model.is_free,
        tool_calling="tools" in params or "tool_choice" in params,
        structured_output="response_format" in params,
        reasoning="reasoning" in params or "reasoning_effort" in params,
        account_available=True,
        runtime_supported=text_output,
        compatibility_reason=None if text_output else "Model does not return text for the LLM slot",
    )


async def account_status(client: OpenRouterClient, credential_id: str) -> OpenRouterAccountResponse:
    try:
        key = await client.key()
        credits = await client.credits()
        return OpenRouterAccountResponse(
            credential_id=credential_id,
            label=key.label,
            valid=True,
            is_free_tier=key.is_free_tier,
            limit=key.limit,
            limit_remaining=key.limit_remaining,
            usage=key.usage,
            usage_daily=key.usage_daily,
            usage_monthly=key.usage_monthly,
            credits_total=credits.total_credits,
            credits_usage=credits.total_usage,
            free_model_daily_requests=key.free_model_daily_requests,
            checked_at=datetime.now(UTC),
        )
    except OpenRouterError as error:
        return OpenRouterAccountResponse(
            credential_id=credential_id,
            valid=False,
            error_category=error.category,
            checked_at=datetime.now(UTC),
        )


async def model_catalog(client: OpenRouterClient, query: OpenRouterModelQuery) -> ModelCatalogResponse:
    page = await client.models(user=True, offset=0, limit=1000, output_modalities="text")
    items = [_option(model) for model in page.data]
    if query.q:
        needle = query.q.casefold()
        items = [item for item in items if needle in item.id.casefold() or needle in item.name.casefold()]
    if query.author:
        author = query.author.casefold()
        items = [item for item in items if (item.author or "").casefold() == author]
    if query.free_only is not None:
        items = [item for item in items if item.is_free == query.free_only]
    if query.tool_calling is not None:
        items = [item for item in items if item.tool_calling == query.tool_calling]
    if query.structured_output is not None:
        items = [item for item in items if item.structured_output == query.structured_output]
    if query.reasoning is not None:
        items = [item for item in items if item.reasoning == query.reasoning]
    if query.min_context is not None:
        items = [item for item in items if (item.context_length or 0) >= query.min_context]
    if query.max_prompt_price is not None:
        items = [item for item in items if item.pricing.prompt <= query.max_prompt_price]
    total = len(items)
    end = query.offset + query.limit
    return ModelCatalogResponse(
        items=items[query.offset:end],
        total_count=total,
        next_offset=end if end < total else None,
        checked_at=datetime.now(UTC),
    )
