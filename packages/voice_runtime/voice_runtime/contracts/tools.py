"""Versioned tool definitions and agent-local binding keys."""

from typing import Any, Literal

from pydantic import Field, HttpUrl, model_validator

from .base import ConfigModel, Identifier


class ToolBinding(ConfigModel):
    tool_id: Identifier
    tool_version_id: Identifier


class WaitConfig(ConfigModel):
    mode: Literal["silent_wait", "acknowledge_then_wait"] = "silent_wait"
    acknowledgement: str | None = None

    @model_validator(mode="after")
    def acknowledgement_required(self):
        if self.mode == "acknowledge_then_wait" and not self.acknowledgement:
            raise ValueError("acknowledge_then_wait requires acknowledgement")
        return self


class RetryConfig(ConfigModel):
    max_attempts: int = Field(default=1, ge=1, le=5)
    backoff_secs: float = Field(default=1, ge=0)
    provider_idempotency_supported: bool = False


class WhatsAppTemplateHeader(ConfigModel):
    """Meta-hosted media reference used directly by a template send."""

    format: Literal["IMAGE", "VIDEO", "DOCUMENT"]
    media_id: str = Field(min_length=1, max_length=120, pattern=r"^[0-9]+$")


class WhatsAppTemplateConfig(ConfigModel):
    """Account-scoped WhatsApp template settings for a registered tool."""

    connection_id: Identifier
    template_name: str = Field(min_length=1, max_length=512)
    language: str = Field(min_length=2, max_length=32)
    header: WhatsAppTemplateHeader | None = None
    parameter_mappings: dict[str, Identifier] = Field(default_factory=dict)


class HTTPToolConfig(ConfigModel):
    url: HttpUrl
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = "POST"
    argument_mapping: dict[str, str] = Field(default_factory=dict)
    secret_reference: Identifier | None = None
    output_extraction: dict[str, str] = Field(default_factory=dict)
    timeout_secs: float = Field(default=10, gt=0, le=120)
    follow_redirects: Literal[False] = False
    retry: RetryConfig = Field(default_factory=RetryConfig)

    @model_validator(mode="after")
    def validate_request(self):
        if self.url.username or self.url.password:
            raise ValueError("URL credentials are forbidden; use a secret reference")
        if self.method != "GET" and self.retry.max_attempts > 1:
            if not self.retry.provider_idempotency_supported:
                raise ValueError("write retries require provider-supported idempotency")
        return self


class ToolConfig(ConfigModel):
    name: Identifier
    description: str = ""
    kind: Literal["registered", "http"] = "registered"
    handler: Identifier | None = None
    http: HTTPToolConfig | None = None
    whatsapp: WhatsAppTemplateConfig | None = None
    knowledge_base_id: Identifier | None = None
    parameters: dict[str, Any] = Field(default_factory=lambda: {"type": "object", "properties": {}})
    wait: WaitConfig = Field(default_factory=WaitConfig)

    @model_validator(mode="after")
    def implementation_required(self):
        if self.kind == "http" and (self.http is None or self.handler is not None):
            raise ValueError("HTTP tools require http settings and no registered handler")
        if self.kind == "registered" and (not self.handler or self.http is not None):
            raise ValueError("registered tools require a reviewed handler and no HTTP settings")
        if self.kind == "http" and self.whatsapp is not None:
            raise ValueError("HTTP tools cannot contain WhatsApp settings")
        if self.handler != "send_whatsapp_template" and self.whatsapp is not None:
            raise ValueError("WhatsApp settings require the send_whatsapp_template handler")
        if self.handler == "send_whatsapp_template" and self.whatsapp is None:
            raise ValueError("send_whatsapp_template requires WhatsApp settings")
        if self.handler != "query_knowledge_base" and self.knowledge_base_id is not None:
            raise ValueError("knowledge_base_id requires the query_knowledge_base handler")
        return self
