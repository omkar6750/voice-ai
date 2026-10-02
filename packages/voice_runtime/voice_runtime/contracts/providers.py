"""Credential-free settings and runtime capabilities for the supported voice stack."""

from copy import deepcopy
from typing import Literal

from pydantic import Field, model_validator

from .base import ConfigModel

SARVAM_LLM_MODELS = ("sarvam-105b", "sarvam-105b-conversations")


class AudioConfig(ConfigModel):
    sample_rate: Literal[8000, 16000] = 16000
    channels: Literal[1] = 1
    encoding: Literal["pcm_s16le"] = "pcm_s16le"
    frame_ms: Literal[20] = 20


class VADConfig(ConfigModel):
    confidence: float = Field(default=0.5, ge=0, le=1)
    start_secs: float = Field(default=0.1, gt=0)
    stop_secs: float = Field(default=0.8, gt=0)
    min_volume: float = Field(default=0.1, ge=0, le=1)


class STTConfig(ConfigModel):
    provider: Literal["sarvam"] = "sarvam"
    model: Literal["saaras:v3"] = "saaras:v3"


class OpenRouterProviderPreferences(ConfigModel):
    """Safe subset of OpenRouter routing controls persisted in agent snapshots."""

    order: list[str] = Field(default_factory=list)
    only: list[str] = Field(default_factory=list)
    ignore: list[str] = Field(default_factory=list)
    allow_fallbacks: bool | None = None
    data_collection: Literal["allow", "deny"] | None = None
    zdr: bool | None = None
    sort_by: Literal["price", "throughput", "latency"] | None = None
    partition: Literal["none"] | None = None


class LLMFallbackConfig(ConfigModel):
    """Optional first-response failover target for the main conversational LLM."""

    provider: Literal["groq", "gemini", "openrouter", "sarvam", "isoquant"]
    model: str = Field(min_length=1)
    first_token_timeout_seconds: float = Field(default=3.0, ge=0.5, le=10)

    @model_validator(mode="after")
    def validate_sarvam_model(self):
        if self.provider == "sarvam" and self.model not in SARVAM_LLM_MODELS:
            raise ValueError("Select a stable Sarvam chat model supported by the runtime")
        if self.provider == "isoquant" and self.model != "glm-5.3-flash":
            raise ValueError("Select the supported Isoquant model glm-5.3-flash")
        return self


class LLMConfig(ConfigModel):
    provider: Literal["groq", "gemini", "openrouter", "sarvam", "isoquant"] = "groq"
    model: str = Field(default="qwen/qwen3.8-27b", min_length=1)
    temperature: float = Field(default=0.4, ge=0, le=2)
    max_tokens: int = Field(default=180, gt=0)
    top_p: float | None = Field(default=None, gt=0, le=1)
    reasoning_effort: Literal["none", "provider_default", "low", "medium", "high", "max"] = "none"
    models: list[str] = Field(default_factory=list)
    provider_preferences: "OpenRouterProviderPreferences | None" = None

    @model_validator(mode="after")
    def validate_reasoning(self):
        if self.provider == "gemini" and self.reasoning_effort != "provider_default":
            raise ValueError("Gemini reasoning uses the provider default")
        if self.provider == "isoquant" and self.reasoning_effort not in {"low", "high", "max"}:
            raise ValueError("Isoquant reasoning effort must be low, high, or max")
        if self.provider in {"groq", "openrouter"} and self.reasoning_effort not in {
            "none",
            "provider_default",
        }:
            raise ValueError("This provider uses provider-default reasoning or no reasoning")
        if self.provider == "sarvam" and self.reasoning_effort not in {
            "none",
            "provider_default",
            "low",
            "medium",
            "high",
        }:
            raise ValueError(
                "Sarvam reasoning effort must be none, provider_default, low, medium, or high"
            )
        if self.provider == "sarvam" and self.model not in SARVAM_LLM_MODELS:
            raise ValueError("Select a stable Sarvam chat model supported by the runtime")
        if self.provider == "isoquant" and self.model != "glm-5.3-flash":
            raise ValueError("Select the supported Isoquant model glm-5.3-flash")
        if self.provider != "openrouter" and (self.models or self.provider_preferences):
            raise ValueError("OpenRouter routing settings require the openrouter provider")
        return self


class MainLLMConfig(LLMConfig):
    """Conversational LLM settings; fallback intentionally excludes other LLM stages."""

    fallback: LLMFallbackConfig | None = None


class CartesiaGenerationConfig(ConfigModel):
    volume: float | None = Field(default=None, ge=0.5, le=2.0)
    speed: float | None = Field(default=None, ge=0.6, le=1.5)
    emotion: str | None = Field(default=None, min_length=1, max_length=64)


class CartesiaTTSConfig(ConfigModel):
    generation_config: CartesiaGenerationConfig | None = None
    pronunciation_dict_id: str | None = Field(default=None, min_length=1, max_length=128)


class TTSConfig(ConfigModel):
    provider: Literal["sarvam", "cartesia"] = "sarvam"
    model: str = "bulbul:v3"
    voice: str = "ritu"
    language: str = "en-IN"
    pace: float = Field(default=1.0, gt=0)
    cartesia: CartesiaTTSConfig | None = None

    @model_validator(mode="after")
    def validate_provider_model(self):
        expected = {
            "sarvam": "bulbul:v3",
            "cartesia": "sonic-3",
        }[self.provider]
        if self.model != expected:
            raise ValueError(
                f"TTS model '{self.model}' is not supported by provider '{self.provider}'; "
                f"use '{expected}'"
            )
        if self.provider == "sarvam" and self.cartesia is not None:
            raise ValueError("Cartesia settings are unavailable for Sarvam TTS")
        if self.provider == "cartesia" and self.pace != 1.0:
            raise ValueError("Cartesia uses generation_config.speed, not Sarvam pace")
        return self


# This is the runtime-owned capability contract. The API augments these definitions with
# credential/catalog status without importing provider SDKs into the dashboard contract.
RUNTIME_PROVIDER_CAPABILITIES: dict[str, dict] = {
    "sarvam": {
        "slots": ["llm", "stt", "tts"],
        "models_by_slot": {
            "llm": list(SARVAM_LLM_MODELS),
            "stt": ["saaras:v3"],
            "tts": ["bulbul:v3"],
        },
        "languages": ["en-IN", "hi-IN", "mr-IN", "te-IN"],
        "voices": [],
        "fields": {
            "model": {"type": "string", "runtime_supported": True},
            "voice": {"type": "string", "runtime_supported": True},
            "language": {"type": "string", "runtime_supported": True},
            "pace": {"type": "number", "runtime_supported": True},
        },
        "runtime_status": "supported",
    },
    "cartesia": {
        "slots": ["tts"],
        "models_by_slot": {"tts": ["sonic-3"]},
        "languages": [],
        "voices": [],
        "fields": {
            "model": {"type": "string", "runtime_supported": True},
            "voice": {"type": "string", "runtime_supported": True},
            "language": {"type": "string", "runtime_supported": True},
            "pace": {
                "type": "number",
                "runtime_supported": False,
                "description": "Cartesia pace is not wired into the current Pipecat runtime.",
            },
            "generation_config": {"type": "object", "runtime_supported": True},
            "pronunciation_dict_id": {"type": "string", "runtime_supported": True},
        },
        "runtime_status": "supported",
    },
}


def runtime_provider_capability(provider: str) -> dict:
    """Return a defensive copy of one provider's runtime capability definition."""

    try:
        return deepcopy(RUNTIME_PROVIDER_CAPABILITIES[provider])
    except KeyError as exc:
        raise ValueError(f"Unknown runtime provider '{provider}'") from exc


class CallLimits(ConfigModel):
    max_duration_secs: int = Field(default=600, gt=0)
    idle_timeout_secs: int = Field(default=60, gt=0)
    interruptions_enabled: bool = True
