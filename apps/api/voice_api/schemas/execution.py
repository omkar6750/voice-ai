from datetime import datetime
from typing import Literal

from pydantic import Field
from voice_runtime.contracts.base import ConfigModel

from voice_api.schemas.diagnostics import DiagnosticInput


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


class EndpointStatus(ConfigModel):
    checked_at: datetime | None = None
    alive: bool = False
    serial_connected: bool = False
    sim_ready: bool | None = None
    voice_registered: bool | None = None
    data_registered: bool | None = None
    packet_attached: bool | None = None
    can_make_call: bool | None = None
    active_call: bool | None = None
    call_state: str | None = None
    rssi: int | None = None
    signal_quality: int | None = None
    operator: str | None = None
    radio_access: str = "unknown"
    band: str | None = None
    roaming: bool | None = None
    usb_audio_supported: bool | None = None
    usb_audio_active: bool | None = None
    last_error: str | None = None


class RuntimeEndpointResponse(ConfigModel):
    id: str
    name: str
    config: EndpointConfig
    created_at: datetime
    active_run_id: str | None = None
    status: EndpointStatus
    last_seen_at: datetime | None = None
    updated_at: datetime | None = None


class RuntimeEndpointsResponse(ConfigModel):
    endpoints: list[RuntimeEndpointResponse]


class EndpointProbeResponse(ConfigModel):
    id: str
    status: EndpointStatus


class EndpointRecoveryResponse(ConfigModel):
    status: Literal["recovered", "available", "blocked"]
    run_id: str | None = None
    reason: str
    message: str
    endpoint_status: EndpointStatus | None = None
    redialed: Literal[False] = False


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
    diagnostics: list[DiagnosticInput] = Field(default_factory=list, max_length=20)
