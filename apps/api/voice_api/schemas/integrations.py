from pydantic import BaseModel, ConfigDict, Field


class WhatsAppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    phone_number_id: str = Field(pattern=r"^[0-9]+$")
    waba_id: str = Field(pattern=r"^[0-9]+$")
    api_version: str = Field(pattern=r"^v[0-9]+\.0$")


class ConnectionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=1, max_length=120)
    provider: str = Field(pattern="^whatsapp$")
    config: WhatsAppConfig
    enabled: bool = False


class UpdateConnectionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str | None = Field(default=None, min_length=1, max_length=120)
    config: WhatsAppConfig | None = None
    enabled: bool | None = None
    expected_updated_at: str | None = None


class SecretBody(BaseModel):
    value: str = Field(min_length=1, max_length=8192)


class MediaImportBody(BaseModel):
    provider_media_id: str = Field(min_length=1, max_length=120)
    filename: str = Field(min_length=1, max_length=255)
    mime_type: str = Field(min_length=1, max_length=100)
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern="^[a-f0-9]{64}$")


class GenerateTemplateToolBody(BaseModel):
    template_name: str = Field(min_length=1)
    language: str = Field(default="en_US")
    tool_name: str | None = None
    description: str | None = None
