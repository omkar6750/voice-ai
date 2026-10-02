from __future__ import annotations

from typing import Any

import httpx


def build_whatsapp_template_payload(
    *,
    destination: str,
    template_name: str,
    language: str,
    header: dict[str, Any] | None,
    parameter_mappings: dict[str, str],
    arguments: dict[str, Any],
    caller_name: str,
) -> dict:
    """Build the provider request without resolving or rewriting media references."""
    components = []
    header_component = whatsapp_template_header_component(header)
    if header_component is not None:
        components.append(header_component)
    if arguments.get("components"):
        components.extend(arguments["components"])
    elif parameter_mappings:
        body_params = [
            {"type": "text", "text": str(arguments[argument])[:1024]}
            for index, argument in sorted(parameter_mappings.items(), key=lambda item: int(item[0]))
            if arguments.get(argument) is not None
        ]
        components.append({"type": "body", "parameters": body_params})
    else:
        body_params = [{"type": "text", "text": caller_name}]
        if arguments.get("message"):
            body_params.append(
                {"type": "text", "text": " ".join(str(arguments["message"]).split())[:1024]}
            )
        for key in sorted(arguments):
            if key.startswith("param_") and key != "param_1":
                body_params.append({"type": "text", "text": str(arguments[key])[:1024]})
        components.append({"type": "body", "parameters": body_params})
    return {
        "messaging_product": "whatsapp",
        "to": destination,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language or "en"},
            "components": components,
        },
    }


def _retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def _provider_body(response: httpx.Response) -> dict | str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:500]
    return body if isinstance(body, dict) else str(body)


def whatsapp_template_header_component(header: dict[str, Any] | None) -> dict | None:
    """Build Meta's template header component from a pinned provider reference."""
    if header is None:
        return None
    if not isinstance(header, dict):
        raise ValueError("WhatsApp template header configuration is invalid")
    header_type = {"IMAGE": "image", "VIDEO": "video", "DOCUMENT": "document"}.get(
        header.get("format")
    )
    media_id = header.get("media_id")
    if not header_type or not isinstance(media_id, str) or not media_id:
        raise ValueError("WhatsApp template header configuration is invalid")
    return {
        "type": "header",
        "parameters": [{"type": header_type, header_type: {"id": media_id}}],
    }
