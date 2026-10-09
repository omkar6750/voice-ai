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
    elif "serial_io_error" in signals:
        outcome.reason, outcome.confidence = "modem_failure", "confirmed"
    elif "normal call clearing" in text:
        outcome.reason, outcome.confidence = "remote_hangup_likely", "likely"
    # Registration loss supports a diagnosis but cannot alone establish why a call cleared.
    return outcome
