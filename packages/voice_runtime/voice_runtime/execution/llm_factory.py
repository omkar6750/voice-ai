"""One runtime seam for direct and OpenRouter text LLM services."""

from __future__ import annotations

from typing import Any

from pipecat.services.google.llm import GoogleLLMService
from pipecat.services.groq.llm import GroqLLMService

from voice_runtime.execution.credential_keys import stage_api_key


def _settings(config: dict[str, Any], *, system_instruction: str | None = None) -> dict[str, Any]:
    values = {
        "model": config.get("model"),
        "temperature": config.get("temperature", 0.4),
        "max_tokens": config.get("max_tokens", config.get("max_output_tokens", 180)),
    }
    if config.get("top_p") is not None:
        values["top_p"] = config["top_p"]
    if system_instruction is not None:
        values["system_instruction"] = system_instruction
    if config.get("reasoning_effort") is not None:
        values["reasoning_effort"] = config["reasoning_effort"]
    return values


def build_llm_service(settings, config: dict[str, Any], *, stage: str, system_instruction: str | None = None):
    """Build one Pipecat LLM service, resolving only the stage credential."""

    provider = config.get("provider", "groq")
    api_key = stage_api_key(settings, stage, provider)
    if not api_key:
        raise ValueError(f"{provider}_api_key is not configured for {stage}")
    values = _settings(config, system_instruction=system_instruction)

    if provider == "groq":
        values["reasoning_effort"] = "none"
        return GroqLLMService(api_key=api_key, settings=GroqLLMService.Settings(**values))
    if provider == "gemini":
        values.pop("reasoning_effort", None)
        return GoogleLLMService(api_key=api_key, settings=GoogleLLMService.Settings(values))
    if provider == "openrouter":
        preferences = config.get("provider_preferences") or {}
        extra: dict[str, Any] = {}
        if config.get("models"):
            extra["models"] = config["models"]
        if preferences:
            extra["provider"] = {
                **{key: preferences[key] for key in ("order", "only", "ignore") if preferences.get(key)},
                **({"allow_fallbacks": preferences["allow_fallbacks"]}
                   if preferences.get("allow_fallbacks") is not None else {}),
                **({"data_collection": preferences["data_collection"]}
                   if preferences.get("data_collection") else {}),
                **({"zdr": preferences["zdr"]} if preferences.get("zdr") is not None else {}),
                **({"sort": {"by": preferences["sort_by"], **(
                    {"partition": preferences["partition"]}
                    if preferences.get("partition") else {}
                )}} if preferences.get("sort_by") else {}),
            }
        try:
            from pipecat.services.openrouter.llm import OpenRouterLLMService

            values.pop("reasoning_effort", None)
            if extra:
                values["extra"] = extra
            return OpenRouterLLMService(api_key=api_key, settings=OpenRouterLLMService.Settings(**values))
        except ImportError:
            from pipecat.services.openai.llm import OpenAILLMService

            values.pop("provider", None)
            return OpenAILLMService(
                api_key=api_key,
                base_url="https://openrouter.ai/api/v1",
                settings=OpenAILLMService.Settings(**values),
            )
    raise ValueError(f"Unsupported LLM provider: {provider}")
