"""Operator catalog: live chat models, cached in process, and runtime-fixed services."""

import asyncio
import hashlib
import time

import httpx
from voice_runtime.contracts import runtime_provider_capability

from voice_api.core.config import Settings
from voice_api.schemas.providers import ProviderCatalogResponse

_TTL_SECONDS = 6 * 60 * 60
_cache: dict[str, tuple[float, list[str]]] = {}
_lock = asyncio.Lock()


async def _models(provider: str, key: str) -> tuple[list[str], str]:
    cache_key = f"{provider}:{hashlib.sha256(key.encode()).hexdigest()}"
    cached = _cache.get(cache_key)
    if cached and cached[0] > time.monotonic():
        return cached[1], "configured"
    async with _lock:
        cached = _cache.get(cache_key)
        if cached and cached[0] > time.monotonic():
            return cached[1], "configured"
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                if provider == "groq":
                    response = await client.get(
                        "https://api.groq.com/openai/v1/models",
                        headers={"Authorization": f"Bearer {key}"},
                    )
                    response.raise_for_status()
                    models = [
                        item["id"]
                        for item in response.json()["data"]
                        if item.get("active", True)
                        and item.get("id")
                        and not any(word in item["id"] for word in ("whisper", "guard", "tts"))
                    ]
                else:
                    models = []
                    page_token = None
                    while True:
                        params = {"key": key, "pageSize": 1000}
                        if page_token:
                            params["pageToken"] = page_token
                        response = await client.get(
                            "https://generativelanguage.googleapis.com/v1beta/models", params=params
                        )
                        response.raise_for_status()
                        payload = response.json()
                        models.extend(
                            item["name"].removeprefix("models/")
                            for item in payload.get("models", [])
                            if "generateContent" in item.get("supportedGenerationMethods", [])
                            and item.get("name", "").startswith("models/gemini-")
                        )
                        page_token = payload.get("nextPageToken")
                        if not page_token:
                            break
            models = sorted(set(models))
            _cache[cache_key] = (time.monotonic() + _TTL_SECONDS, models)
            return models, "configured"
        except (httpx.HTTPError, KeyError, ValueError, TypeError):
            # Keep a stale catalog on transient provider failures, never fabricate models.
            return (cached[1], "stale") if cached else ([], "unavailable")


async def get_provider_registry(settings: Settings) -> ProviderCatalogResponse:
    providers = []
    for name, key in (("groq", settings.groq_api_key), ("gemini", settings.gemini_api_key)):
        models, status = await _models(name, key) if key else ([], "unconfigured")
        providers.append(
            {
                "provider": name,
                "slots": ["llm"],
                "models": models,
                "models_by_slot": {"llm": models},
                "fields": {
                    "model": {
                        "type": "string",
                        "runtime_supported": True,
                        "description": "Provider model identifier.",
                    }
                },
                "status": status,
                "runtime_status": "supported",
            }
        )
    providers.append(
        {
            "provider": "openrouter",
            "slots": ["llm"],
            "models": [],
            "models_by_slot": {"llm": []},
            "fields": {
                "model": {
                    "type": "string",
                    "runtime_supported": True,
                    "description": "Bind an organization OpenRouter credential to load account models.",
                }
            },
            "status": "unconfigured",
            "runtime_status": "supported",
        }
    )
    providers.append(
        {
            "provider": "isoquant",
            "slots": ["llm"],
            "models": ["glm-5.3-flash"],
            "models_by_slot": {"llm": ["glm-5.3-flash"]},
            "fields": {
                "model": {
                    "type": "string",
                    "runtime_supported": True,
                    "description": "Isoquant GLM-5.3-Flash via streaming Chat Completions.",
                },
                "reasoning_effort": {
                    "type": "string",
                    "runtime_supported": True,
                    "description": "Low, high, or max. Reasoning is always enabled.",
                },
            },
            "status": "configured",
            "runtime_status": "supported",
        }
    )
    for name, key in (("sarvam", settings.sarvam_api_key), ("cartesia", settings.cartesia_api_key)):
        capability = runtime_provider_capability(name)
        catalog_ready = any(capability["models_by_slot"].values())
        providers.append(
            {
                "provider": name,
                "models": sorted(
                    {model for models in capability["models_by_slot"].values() for model in models}
                ),
                # Sarvam's model list is static; organization credential binding
                # is validated separately from this public capability list.
                "status": "configured"
                if (catalog_ready if name == "sarvam" else key)
                else "unconfigured",
                **capability,
            }
        )
    return ProviderCatalogResponse.model_validate({"providers": providers})
