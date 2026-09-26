"""Operator catalog: live chat models, cached in process, and runtime-fixed services."""

import asyncio
import time

import httpx

from voice_api.core.config import Settings

_TTL_SECONDS = 6 * 60 * 60
_cache: dict[str, tuple[float, list[str]]] = {}
_lock = asyncio.Lock()


async def _models(provider: str, key: str) -> tuple[list[str], str]:
    cached = _cache.get(provider)
    if cached and cached[0] > time.monotonic():
        return cached[1], "configured"
    async with _lock:
        cached = _cache.get(provider)
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
            _cache[provider] = (time.monotonic() + _TTL_SECONDS, models)
            return models, "configured"
        except (httpx.HTTPError, KeyError, ValueError, TypeError):
            # Keep a stale catalog on transient provider failures, never fabricate models.
            return (cached[1], "stale") if cached else ([], "unavailable")


async def get_provider_registry(settings: Settings) -> dict:
    providers = []
    for name, key in (("groq", settings.groq_api_key), ("gemini", settings.gemini_api_key)):
        models, status = await _models(name, key) if key else ([], "unconfigured")
        providers.append(
            {
                "provider": name,
                "slots": ["llm"],
                "models": models,
                "models_by_slot": {"llm": models},
                "status": status,
            }
        )
    providers.extend(
        [
            {
                "provider": "sarvam",
                "slots": ["stt", "tts"],
                "models": ["saaras:v3", "bulbul:v3"],
                "models_by_slot": {"stt": ["saaras:v3"], "tts": ["bulbul:v3"]},
                "status": "configured" if settings.sarvam_api_key else "unconfigured",
            },
            {
                "provider": "cartesia",
                "slots": ["tts"],
                "models": ["sonic-3"],
                "models_by_slot": {"tts": ["sonic-3"]},
                "status": "configured" if settings.cartesia_api_key else "unconfigured",
            },
        ]
    )
    return {"providers": providers}
