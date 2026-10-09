"""Sanitize and expose whitelisted contact details and ad metadata for agent prompts."""

from __future__ import annotations

from typing import Any

BLOCKED_CONTACT_FIELDS = {"id", "name", "phone_number", "created_at", "metadata_json"}


def sanitize_contact_variables(
    contact_snapshot: dict[str, Any] | None,
    allowed_variables: list[str] | None,
) -> dict[str, Any]:
    """Extract strictly allowed contact variables and ad metadata without hardcoding fields."""
    if not contact_snapshot or not allowed_variables:
        return {}

    contact_snapshot = dict(contact_snapshot)
    # Old immutable snapshots may only contain a full display name.
    parts = str(contact_snapshot.get("name") or "").split()
    if not contact_snapshot.get("first_name") and parts:
        contact_snapshot["first_name"] = parts[0]
        contact_snapshot["last_name"] = " ".join(parts[1:]) or None
    allowed_set = {"first_name" if var == "name" else var for var in allowed_variables}
    sanitized: dict[str, Any] = {}
    metadata = contact_snapshot.get("metadata_json") or {}

    for var in allowed_set:
        if var in BLOCKED_CONTACT_FIELDS or var.startswith("contact."):
            continue
        sanitized[var] = ""
        # 1. Any non-sensitive contact table field (e.g. name, business, source, language, timezone, etc.)
        if var in contact_snapshot and var not in BLOCKED_CONTACT_FIELDS:
            value = contact_snapshot[var]
            if value is not None:
                sanitized[var] = value
        # 2. Nested ad metadata (e.g. "campaign", "ad_headline", "utm_source")
        elif var in metadata and metadata[var] is not None:
            sanitized[var] = metadata[var]
        elif var.startswith("metadata.") and var.removeprefix("metadata.") in metadata:
            key = var.removeprefix("metadata.")
            if metadata.get(key) is not None:
                sanitized[key] = metadata[key]

    return sanitized
