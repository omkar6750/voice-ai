"""Versioned control contract. Secrets never belong to the compiled snapshot."""

from __future__ import annotations

import hashlib
import json
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PrepareSession(Contract):
    version: Literal[1] = 1
    run_id: UUID
    organization_id: UUID
    generation: UUID
    grant: SecretStr = Field(repr=False)
    expires_at: float
    channel: Literal["browser", "twilio", "sim7600", "text_test"]
    config_hash: str
    snapshot: dict
    credentials: dict[str, SecretStr] = Field(default_factory=dict, repr=False)
    telephony_credentials: dict[str, SecretStr] = Field(default_factory=dict, repr=False)
    destination: str = ""
    from_number: str = ""
    correlation_id: str = ""
    browser_session_id: str = ""
    api_public_base_url: str = ""
    conversation_id: UUID | None = None
    checkpoint: dict | None = None


class SessionIdentity(Contract):
    run_id: UUID
    generation: UUID
    boot_id: UUID


class RuntimeSync(SessionIdentity):
    grant: SecretStr = Field(repr=False)
    records: list[dict] = Field(default_factory=list, max_length=100)
    context_updates: list[dict] = Field(default_factory=list, max_length=100)
    metrics: dict = Field(default_factory=dict)
    diagnostics: list[dict] = Field(default_factory=list, max_length=100)
    diagnostic_sequence: int = Field(default=0, ge=0)
    lifecycle: dict | None = None
    text_records: list[dict] = Field(default_factory=list, max_length=100)
    text_checkpoint: dict | None = None


class ToolRequest(SessionIdentity):
    grant: SecretStr = Field(repr=False)
    invocation_id: UUID
    name: str = Field(min_length=1, max_length=150)
    arguments: dict


class ArtifactRequest(SessionIdentity):
    grant: SecretStr = Field(repr=False)
    artifact_id: UUID
    kind: Literal["input", "output", "mixed", "pipeline_log", "runtime_log"]
    size_bytes: int = Field(ge=1, le=100_000_000)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    duration_seconds: float | None = Field(default=None, ge=0)
    sample_rate: int | None = Field(default=None, ge=1)
    channels: int | None = Field(default=None, ge=1)
    sample_width: int | None = Field(default=None, ge=1)


def configuration_hash(snapshot: dict) -> str:
    return hashlib.sha256(
        json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


class ModemProbe(Contract):
    provider: Literal["sim7600"] = "sim7600"
    at_port: str = Field(pattern=r"^COM[1-9][0-9]*$")
    audio_port: str = Field(pattern=r"^COM[1-9][0-9]*$")
    baudrate: int = Field(default=115200, gt=0)
    at_timeout_secs: float = Field(default=2, gt=0, le=30)
    sample_rates: list[Literal[8000, 16000]] = Field(default_factory=lambda: [16000])
