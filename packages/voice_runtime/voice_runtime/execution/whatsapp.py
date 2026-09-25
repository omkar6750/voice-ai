"""WhatsApp runtime execution helpers and 24-hour inbound window tracking."""

import re
from datetime import UTC, datetime, timedelta


def recipient(value: str) -> str:
    value = value.removeprefix("+")
    cleaned = re.sub(r"[^\d]", "", value)
    if not re.fullmatch(r"[1-9][0-9]{5,14}", cleaned):
        raise ValueError("Expected an international phone number")
    return cleaned


class InboundWindow:
    """Only sender/timestamp survive a webhook; restarting deliberately loses the window."""

    def __init__(self, max_entries: int = 10000):
        self.latest: dict[tuple[str, str], datetime] = {}
        self.max_entries = max_entries

    def observe(self, connection_id: str, sender: str, timestamp: str, *, now=None):
        now = now or datetime.now(UTC)
        try:
            at = datetime.fromtimestamp(int(timestamp), UTC)
            sender = recipient(sender)
        except (ValueError, TypeError, OverflowError, OSError):
            return
        if at > now or now - at >= timedelta(hours=24):
            return
        key = (connection_id, sender)
        for expired in [k for k, v in self.latest.items() if now - v >= timedelta(hours=24)]:
            del self.latest[expired]
        if key not in self.latest and len(self.latest) >= self.max_entries:
            del self.latest[min(self.latest, key=self.latest.get)]
        self.latest[key] = max(at, self.latest.get(key, at))

    def allows_text(self, connection_id: str, to: str, *, now=None) -> bool:
        try:
            target = recipient(to)
        except ValueError:
            return False
        # If connection_id is known, check that specific connection
        if connection_id:
            at = self.latest.get((connection_id, target))
        else:
            # Fall back to checking any connection for this recipient
            matches = [v for (c, s), v in self.latest.items() if s == target]
            at = max(matches) if matches else None

        age = (now or datetime.now(UTC)) - at if at else None
        return age is not None and timedelta(0) <= age < timedelta(hours=24)


# Process-wide shared inbound window
shared_inbound_window = InboundWindow()
