"""Validated, deterministic follow-up routing after discovery classification."""

from typing import Any


def followup_route(result: Any) -> str | None:
    """Do not equate inferred cold/resistant labels with an explicit opt-out."""
    if not isinstance(result, dict) or result.get("status") == "error":
        return None
    temperature = result.get("lead_temperature")
    fit = result.get("service_fit")
    tone = result.get("tone")
    if (
        temperature not in {"hot", "warm", "cold"}
        or fit not in {"strong_fit", "possible_fit", "poor_fit"}
        or tone not in {"receptive", "hesitant", "resistant"}
    ):
        return None
    if fit == "poor_fit":
        return "fit_clarification"
    if temperature == "hot" and fit == "strong_fit" and tone == "receptive":
        return "hot_followup"
    if temperature == "cold":
        return "cold_check"
    return "warm_nurture"
