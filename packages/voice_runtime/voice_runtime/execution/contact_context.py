"""Sanitize and expose whitelisted contact details and ad metadata for agent prompts."""

from __future__ import annotations

from typing import Any

BLOCKED_CONTACT_FIELDS = {"id", "phone_number", "created_at", "metadata_json"}


def sanitize_contact_variables(
    contact_snapshot: dict[str, Any] | None,
    allowed_variables: list[str] | None,
) -> dict[str, Any]:
    """Extract strictly allowed contact variables and ad metadata without hardcoding fields."""
    if not contact_snapshot or not allowed_variables:
        return {}

    allowed_set = set(allowed_variables)
    sanitized: dict[str, Any] = {}
    metadata = contact_snapshot.get("metadata_json") or {}

    for var in allowed_set:
        # 1. Any non-sensitive contact table field (e.g. name, business, source, language, timezone, etc.)
        if var in contact_snapshot and var not in BLOCKED_CONTACT_FIELDS:
            if contact_snapshot[var] is not None:
                sanitized[var] = contact_snapshot[var]
        # 2. Nested ad metadata (e.g. "campaign", "ad_headline", "utm_source")
        elif var in metadata and metadata[var] is not None:
            sanitized[var] = metadata[var]
        elif var.startswith("metadata.") and var.removeprefix("metadata.") in metadata:
            key = var.removeprefix("metadata.")
            if metadata.get(key) is not None:
                sanitized[key] = metadata[key]

    return sanitized
