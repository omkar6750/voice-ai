"""Actionable validation diagnostics without reflecting submitted inputs."""

from functools import lru_cache

# Error messages are authored here, never copied from submitted exceptions.
MESSAGES = {
    "initial_user_task_required": "The initial node responds on entry. Add a nonempty user task message in Flow > Task messages, or disable Responds on entry.",
    "missing": "This field is required.",
    "extra_forbidden": "This field is not supported.",
    "int_parsing": "Enter a whole number.",
    "int_type": "Enter a whole number.",
    "int_from_float": "Enter a whole number without a fractional part.",
    "float_parsing": "Enter a number.",
    "float_type": "Enter a number.",
    "bool_parsing": "Enter true or false.",
    "bool_type": "Enter true or false.",
    "string_type": "Enter text.",
    "string_too_short": "Text is shorter than the allowed minimum.",
    "string_too_long": "Text exceeds the allowed length.",
    "string_pattern_mismatch": "Text does not match the required format.",
    "literal_error": "Choose one of the supported options.",
    "enum": "Choose one of the supported options.",
    "greater_than": "Value must be greater than the configured minimum.",
    "greater_than_equal": "Value is below the allowed minimum.",
    "less_than": "Value must be less than the configured maximum.",
    "less_than_equal": "Value exceeds the allowed maximum.",
    "list_type": "Provide a list.",
    "dict_type": "Provide an object.",
    "too_short": "Provide more items; the list is below the allowed minimum.",
    "too_long": "Too many items; the list exceeds the allowed maximum.",
    "uuid_parsing": "Provide a valid identifier.",
    "datetime_parsing": "Provide a valid date and time.",
    "timezone_aware": "Include a timezone in the date and time.",
    "json_invalid": "The request is not valid JSON.",
    "unbound_prompt_tool": "This prompt references a tool unavailable in this node. Check its spelling, connected tools and conversation fact node selection.",
    "fact_tool_unavailable": "This prompt references a conversation fact tool disabled in this node. Enable the fact here or remove the reference.",
}
STATIC_RULES = {
    "node IDs must be unique": "Node IDs must be unique.",
    "initial_node is missing": "The initial node must exist in the flow.",
    "duplicate transition": "Remove duplicate node transitions.",
    "terminal nodes cannot have outgoing transitions": "A terminal node cannot have outgoing transitions.",
    "all nodes must be reachable from initial_node": "Some nodes cannot be reached from the initial node. Check transitions and tool routing.",
    "each node must have a path to a terminal node": "Every node needs a route to a terminal node.",
    "fact slot keys must be unique": "Conversation fact keys must be unique.",
    "fact slot minimum must not exceed maximum": "The fact minimum cannot exceed its maximum.",
    "fact slot ranges require an integer or number value_type": "Fact ranges require a numeric value type.",
    "fact slot enum must not be empty": "Provide enum options or remove the enum restriction.",
    "callback role keys must be unique": "Callback role keys must be unique.",
    "bookable person references an unknown callback role": "A bookable person references an undefined callback role.",
    "timezone must be a valid IANA timezone": "Choose a valid IANA timezone.",
    "Gemini reasoning uses the provider default": "Gemini reasoning must use the provider default.",
    "This provider uses provider-default reasoning or no reasoning": "Choose provider-default reasoning or no reasoning for this provider.",
}
PREFIX_RULES = {
    "unbound prompt tool references in node ": MESSAGES["unbound_prompt_tool"],
    "unknown tool bindings:": "Some tools are not connected to this agent version.",
    "unknown global tool bindings:": "Some shared tools are not connected to this agent version.",
    "generated flow functions collide with tool bindings:": "A connected tool conflicts with an automatically generated fact or transition tool.",
    "unknown transition from ": "A transition points to an undefined node.",
    "fact slot '": "Check the fact's type, constraints and selected nodes.",
    "function '": "Check the tool routing destinations against the defined nodes.",
    "STT provider '": "Choose the speech model supported by the selected provider.",
}


@lru_cache(maxsize=1)
def schema_fields():
    # OpenAPI is generated exclusively from our declared schemas. Arbitrary
    # dictionary keys and custom validator messages cannot enter this allowlist.
    from voice_api.main import app

    fields = {"body", "query", "path", "header", "cookie"}

    def collect(value):
        if isinstance(value, dict):
            fields.update(value.get("properties", {}).keys())
            for child in value.values():
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    collect(app.openapi())
    return frozenset(fields)


def public_validation_errors(error):
    allowed = schema_fields()
    rows = []
    for item in error.errors()[:20]:
        kind = item.get("type", "")
        message = MESSAGES.get(kind)
        if kind == "value_error":
            raw = item.get("msg", "")
            raw = raw.removeprefix("Value error, ")
            message = STATIC_RULES.get(raw)
            if message is None:
                message = next(
                    (safe for prefix, safe in PREFIX_RULES.items() if raw.startswith(prefix)), None
                )
        loc = [
            part
            if isinstance(part, str) and part in allowed
            else part
            if type(part) is int and 0 <= part <= 100000
            else "[key]"
            for part in item.get("loc", ())
        ]
        rows.append(
            {
                "loc": loc,
                "type": kind if kind in MESSAGES or kind == "value_error" else "validation_error",
                "msg": message or "This field failed validation. Review its configuration.",
            }
        )
    return rows or [{"loc": [], "type": "validation_error", "msg": "Request validation failed."}]
