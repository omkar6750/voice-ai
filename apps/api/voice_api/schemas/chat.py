"""Text testing setup and response contracts."""

import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
