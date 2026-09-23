from typing import Literal

from pydantic import Field
from voice_runtime.contracts.base import ConfigModel


class EndpointConfig(ConfigModel):
    provider: Literal["sim7600"] = "sim7600"
    at_port: str = Field(pattern=r"^COM[1-9][0-9]*$")
    audio_port: str = Field(pattern=r"^COM[1-9][0-9]*$")
    baudrate: int = Field(default=115200, gt=0)
    at_timeout_secs: float = Field(default=2, gt=0, le=30)
    sample_rates: list[Literal[8000, 16000]] = Field(default_factory=lambda: [16000], min_length=1)


class EndpointBody(ConfigModel):
    name: str = Field(min_length=1, max_length=120)
    config: EndpointConfig


class Claim(ConfigModel):
    token: str = Field(min_length=1, max_length=36)
    endpoint_id: str
    lease_seconds: int = Field(default=60, ge=15, le=300)


class Progress(ConfigModel):
    token: str
    status: Literal["running", "completed", "failed"]
    final_state: dict | None = None
    error: str | None = None
    transport_released: bool = False
