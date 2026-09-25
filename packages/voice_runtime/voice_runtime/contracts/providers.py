"""Credential-free settings for the supported voice stack."""

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


class CallLimits(ConfigModel):
    max_duration_secs: int = Field(default=300, gt=0)
    idle_timeout_secs: int = Field(default=60, gt=0)
    interruptions_enabled: bool = True
