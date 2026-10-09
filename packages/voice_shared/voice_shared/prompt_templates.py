"""Plain-text templates, without expression evaluation or recursive substitution."""

import math
import re
from collections.abc import Mapping
from typing import Any

VARIABLE = re.compile(r"\{\{\s*([A-Za-z0-9_.:-]+)\s*\}\}")
TEMPORAL_KEYS = {
    "timezone",
    "local_time_24h",
    "local_time_12h",
    "daypart",
    "day_of_week",
    "country",
    "country_code",
    "greeting_phrase",
    "signoff_phrase",
}


def parse_template(text: str) -> list[dict]:
    """Return reference tokens with source offsets; ordinary prose is untouched."""
    tokens = []
    i = 0
    while i < len(text):
        escaped = text[i] == "\\"
        start = i + 1 if escaped else i
        if text.startswith("[", start):
            end = text.find("]", start + 1)
            tail = text[start + 1 : end if end >= 0 else len(text)]
            # Recognize variable groups, including malformed literal alternatives.
            if tail.lstrip().startswith("{{") or ("|" in tail and "{{" in tail):
                if end < 0:
                    raise ValueError(f"Unclosed fallback expression at offset {i}")
                parts = tail.split("|")
                matches = [VARIABLE.fullmatch(p.strip()) for p in parts]
                if len(parts) < 2 or any(m is None for m in matches):
                    raise ValueError(f"Invalid fallback expression at offset {i}")
                tokens.append(
                    {
                        "start": i,
                        "end": end + 1,
                        "expression": text[i : end + 1],
                        "keys": [m.group(1) for m in matches],
                        "fallback": True,
                        "escaped": escaped,
                    }
                )
                i = end + 1
                continue
        match = VARIABLE.match(text, start)
        if match:
            tokens.append(
                {
                    "start": i,
                    "end": match.end(),
                    "expression": text[i : match.end()],
                    "keys": [match.group(1)],
                    "fallback": False,
                    "escaped": escaped,
                }
            )
            i = match.end()
            continue
        if text.startswith("{{", start):
            raise ValueError(f"Invalid variable reference at offset {i}")
        i += 1
    return tokens


def variable_types(config: dict) -> dict[str, str]:
    return {
        **dict.fromkeys(TEMPORAL_KEYS, "string"),
        **dict.fromkeys(config.get("contact_variables", []), "string"),
        **{s["key"]: s.get("value_type", "string") for s in config.get("fact_slots", [])},
    }


def validate_template(text: str, types: dict[str, str]) -> None:
    for token in parse_template(text):
        if token["escaped"]:
            continue
        for key in token["keys"]:
            if key not in types:
                raise ValueError(f"Unknown prompt variable '{key}' at offset {token['start']}")
            if token["fallback"] and types[key] == "boolean":
                raise ValueError(
                    f"Boolean variable '{key}' cannot be used in a fallback expression"
                )


def empty_reason(value: Any) -> str | None:
    if isinstance(value, str) and not value.strip():
        return "empty_string"
    if not isinstance(value, bool) and isinstance(value, (int, float)) and value == 0:
        return "zero"
    return None


def lookup(state: dict, key: str) -> Any:
    value = state[key] if key in state else state
    for part in [] if key in state else key.split("."):
        if not isinstance(value, Mapping) or part not in value:
            raise ValueError(f"Prompt variable '{key}' is missing from state")
        value = value[part]
    if value is None:
        raise ValueError(f"Prompt variable '{key}' must not be null")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"Prompt variable '{key}' must be finite")
    return value


def render_template(text: str, state: dict, types: dict[str, str], sources: dict | None = None):
    validate_template(text, types)
    pieces, records, cursor = [], [], 0
    for token in parse_template(text):
        pieces.append(text[cursor : token["start"]])
        cursor = token["end"]
        if token["escaped"]:
            pieces.append(token["expression"][1:])
            continue
        candidates = []
        for key in token["keys"]:
            value = lookup(state, key)
            if token["fallback"] and (
                isinstance(value, bool) or not isinstance(value, (str, int, float))
            ):
                raise ValueError(f"Fallback variable '{key}' must be a string or number")
            candidates.append(
                {
                    "key": key,
                    "value": value,
                    "empty_reason": empty_reason(value),
                    "source": (sources or {}).get(key, {"kind": "state"}),
                }
            )
        chosen = (
            next((c for c in reversed(candidates) if c["empty_reason"] is None), None)
            if token["fallback"]
            else candidates[0]
        )
        rendered = str(chosen["value"]) if chosen else ""
        pieces.append(rendered)
        records.append(
            {
                **{k: token[k] for k in ("start", "end", "expression", "fallback")},
                "candidates": candidates,
                "selected_key": chosen["key"] if chosen else None,
                "value": rendered,
                "outcome": "selected" if chosen else "all_empty",
            }
        )
    pieces.append(text[cursor:])
    return "".join(pieces), records


def prompt_fields(node: dict):
    for name in ("role_message", "role_prompt", "prompt"):
        if isinstance(node.get(name), str):
            yield name, node[name]
    for index, message in enumerate(node.get("task_messages", [])):
        if isinstance(message.get("content"), str):
            yield f"task_messages.{index}.content", message["content"]
    for phase in ("pre_actions", "post_actions", "entry_actions", "exit_actions"):
        for index, action in enumerate(node.get(phase, [])):
            if (
                isinstance(action, dict)
                and action.get("type") == "tts_say"
                and isinstance(action.get("text"), str)
            ):
                yield f"{phase}.{index}.text", action["text"]


def render_node(node: dict, state: dict, types: dict, sources: dict | None = None):
    # Native nodes contain executable schemas and bound action handlers. Copy
    # template containers, never their live runtime objects (tasks, transports).
    def copy_containers(value):
        if isinstance(value, dict):
            return {key: copy_containers(item) for key, item in value.items()}
        if isinstance(value, list):
            return [copy_containers(item) for item in value]
        return value

    rendered, records = copy_containers(node), []
    for path, text in prompt_fields(node):
        value, refs = render_template(text, state, types, sources)
        target = rendered
        parts = path.split(".")
        for part in parts[:-1]:
            target = target[int(part)] if isinstance(target, list) else target[part]
        target[parts[-1]] = value
        records.extend({"field": path, **r} for r in refs)
    return rendered, records


def initialize_facts(state: dict, slots: list[dict]) -> dict:
    for slot in slots:
        state.setdefault(slot["key"], slot.get("default_value", ""))
    return state


def validate_config_templates(config: dict) -> None:
    types = variable_types(config)
    fields = [("system_prompt", config.get("system_prompt", ""))]
    for index, node in enumerate(config.get("flow", {}).get("nodes", [])):
        fields.extend((f"flow.nodes.{index}.{path}", text) for path, text in prompt_fields(node))
    for path, text in fields:
        try:
            validate_template(text or "", types)
        except ValueError as exc:
            raise ValueError(f"{path}: {exc}") from exc
