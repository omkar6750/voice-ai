"""Runtime handler capabilities shared by the API and the native host."""

from typing import Any

from pydantic import Field

from .base import ConfigModel, Identifier


class RegisteredHandlerSpec(ConfigModel):
    """The public contract for one in-process registered tool handler."""

    name: Identifier
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    runtime_supported: bool = True
    category: Identifier


_HANDLER_SPECS: tuple[RegisteredHandlerSpec, ...] = (
    RegisteredHandlerSpec(
        name="change_node",
        description="Transfer conversation flow to another connected node in the agent flow graph.",
        parameters={
            "type": "object",
            "properties": {
                "node": {
                    "type": "string",
                    "description": "Identifier key of the destination node",
                }
            },
            "required": ["node"],
        },
        category="flow",
    ),
    RegisteredHandlerSpec(
        name="end_call",
        description="Terminate and hang up the current phone call.",
        parameters={
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Optional closing explanation or reason",
                }
            },
        },
        category="telephony",
    ),
    RegisteredHandlerSpec(
        name="send_whatsapp_template",
        description="Send an approved WhatsApp template with dynamic body parameters to the contact.",
        parameters={
            "type": "object",
            "properties": {
                "to": {
                    "type": "string",
                    "description": "Optional destination international phone number (defaults to contact's phone)",
                },
                "caller_name": {
                    "type": "string",
                    "description": "Recipient name for template personalization",
                },
                "message": {
                    "type": "string",
                    "description": "Dynamic summary or body text for the template",
                },
            },
        },
        category="messaging",
    ),
    RegisteredHandlerSpec(
        name="check_whatsapp_window",
        description="Verify whether an active 24-hour customer service window exists based on inbound messages.",
        parameters={
            "type": "object",
            "properties": {
                "to": {
                    "type": "string",
                    "description": "E.164 phone number of the contact",
                }
            },
            "required": ["to"],
        },
        category="messaging",
    ),
    RegisteredHandlerSpec(
        name="send_whatsapp_message",
        description="Send a direct freeform WhatsApp text within the active 24-hour customer service window.",
        parameters={
            "type": "object",
            "properties": {
                "to": {
                    "type": "string",
                    "description": "E.164 phone number of the contact",
                },
                "text": {"type": "string", "description": "Message text to send"},
            },
            "required": ["to", "text"],
        },
        category="messaging",
    ),
    RegisteredHandlerSpec(
        name="classify_lead",
        description="Classify the live lead using the classifier backend configured for this agent.",
        category="classification",
    ),
    RegisteredHandlerSpec(
        name="check_callback_availability",
        description="Find available human callback slots within a caller-requested timeframe and configured role.",
        parameters={
            "type": "object",
            "properties": {
                "timeframe": {"type": "string"},
                "role": {"type": "string"},
                "duration_minutes": {"type": "integer"},
            },
            "required": ["timeframe", "role"],
        },
        category="cadence",
    ),
    RegisteredHandlerSpec(
        name="book_callback",
        description="Book one slot returned by check_callback_availability on the selected employee calendar.",
        parameters={
            "type": "object",
            "properties": {"slot_id": {"type": "string"}, "reason": {"type": "string"}},
            "required": ["slot_id", "reason"],
        },
        category="cadence",
    ),
    RegisteredHandlerSpec(
        name="schedule_callback",
        description="Schedule an automated or operator callback based on caller request or spoken phrases.",
        parameters={
            "type": "object",
            "properties": {
                "time": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["time"],
        },
        category="cadence",
    ),
    RegisteredHandlerSpec(
        name="query_knowledge_base",
        description="Search the agent's attached knowledge base using hybrid retrieval.",
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        category="knowledge",
    ),
)


def registered_handler_specs() -> list[RegisteredHandlerSpec]:
    """Return detached specs so callers cannot mutate the canonical registry."""

    return [spec.model_copy(deep=True) for spec in _HANDLER_SPECS]


def registered_handler_names() -> frozenset[str]:
    return frozenset(spec.name for spec in _HANDLER_SPECS if spec.runtime_supported)


def is_registered_handler(name: str | None) -> bool:
    return bool(name and name in registered_handler_names())
