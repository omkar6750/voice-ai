"""Conservative release interpretation; observations are not proof of an initiator."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class CallOutcome:
    reason: str = "disconnect_unknown"
    confidence: str = "unknown"
    release_report: str | None = None
    query_errors: list[str] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    registration: dict = field(default_factory=dict)

    def snapshot(self) -> dict:
        return asdict(self)


def determine_outcome(
    *, events: list[dict], report: str | None, errors: list[str], registration: dict
) -> CallOutcome:
    outcome = CallOutcome(
        release_report=report, query_errors=errors, events=events, registration=registration
    )
    # Never interpret a naked numeric CEER: internal and network cause domains overlap.
    text = (report or "").lower()
    signals = {event.get("signal") for event in events}
    local = next((e["observed_at_ns"] for e in events if e.get("signal") == "local_hangup"), None)
    cleared = next(
        (
            e["observed_at_ns"]
            for e in events
            if e.get("signal") in {"call_cleared", "NO CARRIER", "BUSY", "NO ANSWER"}
            or str(e.get("signal", "")).startswith("VOICE CALL END")
        ),
        None,
    )
    if local is not None and (cleared is None or local < cleared):
        outcome.reason, outcome.confidence = "local_hangup", "confirmed"
        return outcome
    if "BUSY" in signals or "user busy" in text:
        outcome.reason, outcome.confidence = "busy", "confirmed"
    elif "NO DIALTONE" in signals:
        outcome.reason, outcome.confidence = "dial_failed", "confirmed"
    elif "NO ANSWER" in signals or any(
        value in text for value in ("no user responding", "user alerting, no answer")
    ):
        outcome.reason, outcome.confidence = "no_answer", "confirmed"
    elif any(value in text for value in ("call rejected", "call rejection")):
        outcome.reason, outcome.confidence = "call_rejected", "confirmed"
    elif any(
        value in text
        for value in (
            "network out of order",
            "temporary failure",
            "switching equipment congestion",
            "no service available",
            "no circuit/channel available",
            "radio link failure",
        )
    ):
        outcome.reason, outcome.confidence = "network_failure", "confirmed"
    elif any(
        event.get("signal") == "voice_registration_lost"
        and (cleared is None or event.get("observed_at_ns", 0) <= cleared)
        for event in events
    ):
        outcome.reason, outcome.confidence = "network_failure", "high"
    elif "serial_io_error" in signals:
        outcome.reason, outcome.confidence = "modem_failure", "confirmed"
    elif (
        cleared is not None
        and not errors
        and registration.get("voice_registered") is True
        and isinstance(registration.get("rssi"), int)
        and registration["rssi"] >= 15
        and not any(
            event.get("signal") in {"serial_io_error", "voice_registration_lost"}
            for event in events
        )
    ):
        # Operational attribution rule: no local release, modem remained registered
        # with usable signal, and no transport/network fault was observed. This is a
        # high-confidence other-side release classification, not a carrier-supplied
        # identity for the party that sent the release.
        outcome.reason, outcome.confidence = "remote_hangup", "high"
    elif "normal call clearing" in text:
        outcome.reason, outcome.confidence = "remote_hangup_likely", "likely"
    # Registration loss supports a diagnosis but cannot alone establish why a call cleared.
    return outcome
