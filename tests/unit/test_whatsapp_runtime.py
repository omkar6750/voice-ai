"""Unit tests for WhatsApp 24h inbound window tracking and fail-closed direct messaging."""

from datetime import UTC, datetime, timedelta

from voice_runtime.execution.whatsapp import InboundWindow, recipient


def test_recipient_normalization():
    assert recipient("+1 (555) 123-4567") == "15551234567"
    assert recipient("919876543210") == "919876543210"
    assert recipient("+91 98765 43210") == "919876543210"


def test_inbound_window_allows_and_expires():
    window = InboundWindow()
    now = datetime(2026, 9, 25, 12, 0, 0, tzinfo=UTC)

    # Unknown number fails closed
    assert window.allows_text("conn1", "+15551234567", now=now) is False

    # Observe incoming message 1 hour ago
    one_hour_ago = int((now - timedelta(hours=1)).timestamp())
    window.observe("conn1", "+15551234567", str(one_hour_ago), now=now)

    # Window is open for conn1
    assert window.allows_text("conn1", "+15551234567", now=now) is True

    # 25 hours later, window is closed
    twenty_five_hours_later = now + timedelta(hours=25)
    assert window.allows_text("conn1", "+15551234567", now=twenty_five_hours_later) is False


def test_inbound_window_rejects_stale_or_future_observations():
    window = InboundWindow()
    now = datetime(2026, 9, 25, 12, 0, 0, tzinfo=UTC)

    # Stale observation (> 24 hours in past) is rejected
    stale_timestamp = int((now - timedelta(hours=25)).timestamp())
    window.observe("conn1", "+15551234567", str(stale_timestamp), now=now)
    assert window.allows_text("conn1", "+15551234567", now=now) is False

    # Future observation is rejected
    future_timestamp = int((now + timedelta(hours=1)).timestamp())
    window.observe("conn1", "+15551234567", str(future_timestamp), now=now)
    assert window.allows_text("conn1", "+15551234567", now=now) is False
