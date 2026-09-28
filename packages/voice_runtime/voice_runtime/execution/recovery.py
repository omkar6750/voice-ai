"""Safe compatibility normalization for explicitly approved evidence replay."""


def normalize_known_diagnostic(record: dict) -> tuple[dict, bool]:
    """Remove only the known progress-envelope timestamp from evidence diagnostics."""
    if record.get("kind") != "diagnostic" or "occurred_at" not in record:
        return record, False
    normalized = {key: value for key, value in record.items() if key != "occurred_at"}
    return normalized, True
