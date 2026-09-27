from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class WhatsAppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    phone_number_id: str = Field(pattern=r"^[0-9]+$")
    waba_id: str = Field(pattern=r"^[0-9]+$")
    api_version: str = Field(pattern=r"^v[0-9]+\.0$")


class TwilioPhoneNumber(BaseModel):
    model_config = ConfigDict(extra="ignore")
    sid: str
    phone_number: str
    friendly_name: str | None = None
    voice: bool = True


class TwilioVoiceConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    account_sid: str = Field(pattern=r"^AC[a-zA-Z0-9]{32}$")
    phone_numbers: list[TwilioPhoneNumber] = Field(default_factory=list)
    account_type: str | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_secrets(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "auth_token" in data or "secret" in data:
                raise ValueError("Secrets cannot be stored in connection config")
        return data


class ConnectionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=1, max_length=120)
    provider: str = Field(pattern=r"^(whatsapp|twilio_voice)$")
    config: WhatsAppConfig | TwilioVoiceConfig
    enabled: bool = False

    @model_validator(mode="after")
    def validate_provider_config(self) -> "ConnectionBody":
        if self.provider == "whatsapp" and not isinstance(self.config, WhatsAppConfig):
            raise ValueError("Config does not match whatsapp schema")
        if self.provider == "twilio_voice" and not isinstance(self.config, TwilioVoiceConfig):
            raise ValueError("Config does not match twilio_voice schema")
        return self


class UpdateConnectionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str | None = Field(default=None, min_length=1, max_length=120)
    config: WhatsAppConfig | TwilioVoiceConfig | None = None
    enabled: bool | None = None
    expected_updated_at: str | None = None


class SecretBody(BaseModel):
    value: str = Field(min_length=1, max_length=8192)


class MediaImportBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_media_id: str = Field(min_length=1, max_length=120)
    display_name: str = Field(min_length=1, max_length=255)
    media_type: Literal["image", "video", "document", "audio"]
    mime_type: str = Field(default="application/octet-stream", min_length=1, max_length=100)
    original_filename: str | None = Field(default=None, max_length=255)
    size_bytes: int = Field(default=0, ge=0)
    sha256: str | None = Field(default=None, pattern="^[a-f0-9]{64}$")
    provider_metadata: dict[str, Any] = Field(default_factory=dict)


class MediaUpdateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=255)


class MediaResponse(BaseModel):
    id: str
    connection_id: str
    provider_media_id: str
    display_name: str
    filename: str
    media_type: Literal["image", "video", "document", "audio"]
    mime_type: str
    size_bytes: int
    sha256: str | None
    source: Literal["uploaded", "imported"]
    status: Literal["available", "unverified", "unavailable", "deleted"]
    provider_metadata: dict[str, Any]
    uploaded_at: datetime
    last_verified_at: datetime | None


class MediaListResponse(BaseModel):
    media: list[MediaResponse]


class GenerateTemplateToolBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template_name: str = Field(min_length=1)
    language: str = Field(default="en_US")
    tool_name: str | None = None
    description: str | None = None
    header_media_id: str | None = None
    parameter_descriptions: dict[str, str] = Field(default_factory=dict)
    parameter_mappings: dict[str, str] = Field(default_factory=dict)


class GeneratedTemplateToolResponse(BaseModel):
    tool_id: str
    tool_version_id: str
    name: str
    tool_name: str
    version: int
    version_number: int
    extracted_variables: list[str]
    config: dict[str, Any]
