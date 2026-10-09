"""Text testing setup and response contracts."""

import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CreateChat(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent_version_id: UUID
    contact_id: UUID | None = None
    whatsapp_number: str | None = None
    starting_node: str | None = Field(default=None, max_length=100)
    caller_background: str = Field(default="", max_length=4000)
    scenario: Literal[
        "manual", "interested", "hesitant", "busy", "mismatch", "multilingual", "opt_out"
    ] = "manual"

    @field_validator("whatsapp_number")
    @classmethod
    def phone(cls, value):
        if not value:
            return None
        if not re.fullmatch(r"\+[1-9]\d{6,14}", value):
            raise ValueError("Use an international phone number, for example +919876543210")
        return value


class ChatTestTurn(BaseModel):
    """One compact MCP interaction with a saved text-test conversation."""

    model_config = ConfigDict(extra="forbid")
    agent_version_id: UUID | None = None
    conversation_id: UUID | None = None
    contact_id: UUID | None = None
    caller_message: str | None = Field(default=None, min_length=1, max_length=8000)
    caller_background: str = Field(default="", max_length=4000)
    starting_node: str | None = Field(default=None, max_length=100)
    scenario: Literal[
        "manual", "interested", "hesitant", "busy", "mismatch", "multilingual", "opt_out"
    ] = "manual"

    @model_validator(mode="after")
    def conversation_or_version(self):
        if (self.conversation_id is None) == (self.agent_version_id is None):
            raise ValueError("Provide exactly one of conversation_id or agent_version_id")
        if self.conversation_id is not None and self.contact_id is not None:
            raise ValueError("contact_id can only be set when starting a conversation")
        if self.conversation_id is not None and self.caller_message is None:
            raise ValueError("caller_message is required when continuing a conversation")
        return self


class ChatSummary(BaseModel):
    id: str
    agent_version_id: str
    revision: int
    status: str
    scenario: str
    destination: str
    created_at: str
    error: dict | None = None


class ChatTicket(BaseModel):
    ws_url: str
    run_id: str
    conversation_id: str
