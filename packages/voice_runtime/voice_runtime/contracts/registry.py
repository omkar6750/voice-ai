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
    node_action_supported: bool = False
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
        node_action_supported=True,
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
        description=(
            "Find available human callback slots within a caller-requested timeframe and "
            "configured role. Offer returned display labels exactly as written because they "
            "are speech-ready local times; never read slot IDs or timezone identifiers aloud."
        ),
        parameters={
            "type": "object",
            "properties": {
                "timeframe": {"type": "string"},
                "role": {"type": "string"},
            },
            "required": ["timeframe", "role"],
        },
        category="cadence",
    ),
    RegisteredHandlerSpec(
        name="book_callback",
        description=(
            "Book the caller-selected slot using the complete, unchanged slot_id returned by "
            "check_callback_availability. Wait for a successful result before confirming."
        ),
        parameters={
            "type": "object",
            "properties": {"slot_id": {"type": "string"}, "reason": {"type": "string"}},
            "required": ["slot_id", "reason"],
        },
        category="cadence",
    ),
    RegisteredHandlerSpec(
        name="schedule_callback",
        description=(
            "Record a callback request for the contact's local date and time. An operator can "
            "launch the callback from the callback queue; this tool does not place a future call."
        ),
        parameters={
            "type": "object",
            "properties": {
                "time": {"type": "string"},
                "reason": {"type": "string"},
                "timezone": {
                    "type": "string",
                    "description": "IANA timezone, required only when the contact timezone is unknown",
                },
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


def supports_node_action(definition: dict[str, Any]) -> bool:
    """Whether a registered tool can run without model-supplied arguments."""
    if definition.get("kind") != "registered":
        return False
    spec = next(
        (item for item in _HANDLER_SPECS if item.name == definition.get("handler")),
        None,
    )
    required = definition.get("parameters", {}).get("required", [])
    return bool(spec and spec.runtime_supported and spec.node_action_supported and not required)


def validate_node_actions(config: dict[str, Any], tools: dict[str, dict[str, Any]]) -> list[str]:
    """Return actionable errors for configured lifecycle actions and background hooks."""
    errors = []
    if config.get("background_hooks"):
        errors.append("Background hooks are not supported by the live runtime")
    for node in config.get("flow", {}).get("nodes", []):
        for phase in ("entry", "exit"):
            for binding_key in node.get(f"{phase}_actions", []):
                binding = tools.get(binding_key, {})
                definition = binding.get("definition", binding)
                if not supports_node_action(definition):
                    errors.append(
                        f"{phase.title()} action '{binding_key}' on node '{node.get('id', '')}' "
                        "is not supported by the live runtime"
                    )
    return errors
