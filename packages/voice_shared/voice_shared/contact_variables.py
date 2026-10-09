"""Canonical flat contact prompt variables and legacy prompt translation."""

import re
from copy import deepcopy
from typing import Any


def normalize_contact_prompt(text: str) -> str:
    """Translate old aliases without rewriting prose or unrelated variables."""

    def replace(match):
        key = match.group(1)
        key = key.removeprefix("contact.")
        return "{{" + ("first_name" if key == "name" else key) + "}}"

    return re.sub(
        r"(?<!\\)\{\{\s*(name|contact\.[A-Za-z_][A-Za-z0-9_.]*)\s*\}\}",
        replace,
        text,
    )


def normalize_contact_config(config: dict[str, Any]) -> dict[str, Any]:
    """Return a copy: stored publications and historical snapshots stay immutable."""
    result = deepcopy(config)
    variables = [
        "first_name" if key.removeprefix("contact.") == "name" else key.removeprefix("contact.")
        for key in result.get("contact_variables", [])
    ]
    result["contact_variables"] = list(dict.fromkeys(variables))
    for key in ("system_prompt", "greeting", "idle_reprompt_text"):
        if isinstance(result.get(key), str):
            result[key] = normalize_contact_prompt(result[key])
    for node in result.get("flow", {}).get("nodes", []):
        for key in ("prompt", "role_message", "role_prompt"):
            if isinstance(node.get(key), str):
                node[key] = normalize_contact_prompt(node[key])
        for message in node.get("task_messages", []):
            message["content"] = normalize_contact_prompt(message["content"])
        for key in ("pre_actions", "post_actions"):
            for action in node.get(key, []):
                if isinstance(action.get("text"), str):
                    action["text"] = normalize_contact_prompt(action["text"])
    return result
