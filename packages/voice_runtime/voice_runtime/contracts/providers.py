"""Credential-free settings and runtime capabilities for the supported voice stack."""

from copy import deepcopy
from typing import Literal

from pydantic import Field, model_validator

from .base import ConfigModel


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


class LLMConfig(ConfigModel):
    provider: Literal["groq", "gemini"] = "groq"
    model: str = Field(default="qwen/qwen3.8-27b", min_length=1)
    temperature: float = Field(default=0.4, ge=0, le=2)
    max_tokens: int = Field(default=180, gt=0)
    top_p: float | None = Field(default=None, gt=0, le=1)
    reasoning_effort: Literal["none", "provider_default"] = "none"

    @model_validator(mode="after")
    def validate_reasoning(self):
        if self.provider == "gemini" and self.reasoning_effort != "provider_default":
            raise ValueError("Gemini reasoning uses the provider default")
        if self.provider == "groq" and self.reasoning_effort != "none":
            raise ValueError("Groq reasoning is disabled in this runtime")
        return self


class TTSConfig(ConfigModel):
    provider: Literal["sarvam", "cartesia"] = "sarvam"
    model: str = "bulbul:v3"
    voice: str = "ritu"
    language: str = "en-IN"
    pace: float = Field(default=1.0, gt=0)

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
        return self


# This is the runtime-owned capability contract. The API augments these definitions with
# credential/catalog status without importing provider SDKs into the dashboard contract.
RUNTIME_PROVIDER_CAPABILITIES: dict[str, dict] = {
    "sarvam": {
        "slots": ["stt", "tts"],
        "models_by_slot": {"stt": ["saaras:v3"], "tts": ["bulbul:v3"]},
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
    max_duration_secs: int = Field(default=300, gt=0)
    idle_timeout_secs: int = Field(default=60, gt=0)
    interruptions_enabled: bool = True
