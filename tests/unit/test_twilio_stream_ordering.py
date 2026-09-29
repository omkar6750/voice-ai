from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from voice_api.models import Call
from voice_api.services.call_service import (
    apply_twilio_call_status,
    apply_twilio_stream_status,
)


def setup(*, status="active", metadata=None, locked_call=True):
    passed_call = Call(
        id="call-1",
        run_id="run-1",
        contact_id="contact-1",
        agent_version_id="agent-1",
        provider="twilio",
        status=status,
        provider_metadata={"stream_sid": "MZ-pinned", **(metadata or {})},
    )
    refreshed_call = Call(
        id=passed_call.id,
        run_id=passed_call.run_id,
        contact_id=passed_call.contact_id,
        agent_version_id=passed_call.agent_version_id,
        provider=passed_call.provider,
        status=status,
        provider_metadata={"stream_sid": "MZ-pinned", **(metadata or {})},
    )
    session = AsyncMock(spec=AsyncSession)
    session.get.return_value = refreshed_call if locked_call else None
    return session, passed_call, refreshed_call


@pytest.mark.asyncio
@pytest.mark.parametrize("event", [None, "", "unknown"])
async def test_missing_or_unknown_event_is_ignored(event):
    session, call, _ = setup()

    await apply_twilio_stream_status(
        session, call, stream_sid="MZ-pinned", event=event, error="secret"
    )

    session.get.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_stream_sid_is_ignored():
    session, call, _ = setup()

    await apply_twilio_stream_status(
        session, call, stream_sid=None, event="stream-started", error=None
    )

    session.get.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_disappeared_locked_call_is_ignored():
    session, call, _ = setup(locked_call=False)

    await apply_twilio_stream_status(
        session, call, stream_sid="MZ-pinned", event="stream-started", error=None
    )

    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_mismatched_stream_sid_is_ignored():
    session, _, refreshed = setup()

    await apply_twilio_stream_status(
        session, refreshed, stream_sid="MZ-other", event="stream-stopped", error=None
    )

    assert refreshed.provider_metadata.get("stream_status") is None
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal_status", ["stopped", "error"])
async def test_late_started_event_does_not_regress_terminal_stream(terminal_status):
    session, _, refreshed = setup(metadata={"stream_status": terminal_status})

    await apply_twilio_stream_status(
        session, refreshed, stream_sid="MZ-pinned", event="stream-started", error=None
    )

    assert refreshed.provider_metadata["stream_status"] == terminal_status
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_stream_error_persists_only_generic_message():
    session, _, refreshed = setup()
    private_error = "token=secret provider response body"

    await apply_twilio_stream_status(
        session,
        refreshed,
        stream_sid="MZ-pinned",
        event="stream-error",
        error=private_error,
    )

    assert refreshed.provider_metadata["stream_status"] == "error"
    assert refreshed.provider_metadata["stream_error"] == "Twilio reported a stream error"
    assert private_error not in str(refreshed.provider_metadata)
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_stream_update_locks_and_mutates_refreshed_call():
    session, passed, refreshed = setup(metadata={"stale": True})

    await apply_twilio_stream_status(
        session, passed, stream_sid="MZ-pinned", event="stream-started", error=None
    )

    session.get.assert_awaited_once_with(
        Call, passed.id, with_for_update=True, populate_existing=True
    )
    assert refreshed.provider_metadata["stream_status"] == "started"
    assert "stream_status" not in passed.provider_metadata
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_started_event_does_not_activate_terminal_call():
    session, _, refreshed = setup(status="completed")

    await apply_twilio_stream_status(
        session, refreshed, stream_sid="MZ-pinned", event="stream-started", error=None
    )

    assert "stream_status" not in refreshed.provider_metadata
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_call_status_ignores_disappeared_locked_call():
    session, passed, _ = setup(status="ringing", locked_call=False)

    await apply_twilio_call_status(session, passed, "in-progress")

    assert passed.status == "ringing"
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_call_status_mutates_refreshed_locked_call():
    session, passed, refreshed = setup(status="ringing")

    await apply_twilio_call_status(session, passed, "in-progress")

    assert refreshed.status == "active"
    assert passed.status == "ringing"
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_first_queued_callback_binds_sid_without_regressing_call():
    session, passed, refreshed = setup(status="dialing", metadata={})

    await apply_twilio_call_status(
        session,
        passed,
        "queued",
        sequence_number=3,
        provider_call_id="CA-first-callback",
    )

    assert refreshed.status == "dialing"
    assert refreshed.provider_call_id == "CA-first-callback"
    assert refreshed.provider_metadata["twilio_status"] == "queued"
    assert refreshed.provider_metadata["twilio_raw_status"] == "queued"
    assert refreshed.provider_metadata["twilio_sequence_number"] == 3
    assert passed.status == "dialing"
    assert passed.provider_call_id is None
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_call_status_rechecks_pinned_sid_on_locked_row():
    session, passed, refreshed = setup()
    refreshed.provider_call_id = "CA-original"

    with pytest.raises(ValueError, match="Call SID does not match") as caught:
        await apply_twilio_call_status(
            session,
            passed,
            "in-progress",
            provider_call_id="CA-raced",
        )

    assert "CA-original" not in str(caught.value)
    assert "CA-raced" not in str(caught.value)
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_first_accepted_call_status_binds_provider_sid():
    session, passed, refreshed = setup()

    await apply_twilio_call_status(
        session, passed, "in-progress", provider_call_id="CA-first"
    )

    assert refreshed.provider_call_id == "CA-first"
    assert passed.provider_call_id is None
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_unknown_call_status_does_not_bind_provider_sid():
    session, passed, refreshed = setup()

    await apply_twilio_call_status(
        session, passed, "unknown", provider_call_id="CA-untrusted"
    )

    assert refreshed.provider_call_id is None
    session.get.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_stream_status_rechecks_pinned_sid_on_locked_row():
    session, passed, refreshed = setup()
    refreshed.provider_call_id = "CA-original"

    with pytest.raises(ValueError, match="Call SID does not match") as caught:
        await apply_twilio_stream_status(
            session,
            passed,
            stream_sid="MZ-pinned",
            event="stream-started",
            error=None,
            provider_call_id="CA-raced",
        )

    assert "CA-original" not in str(caught.value)
    assert "CA-raced" not in str(caught.value)
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_first_accepted_stream_event_binds_provider_sid():
    session, passed, refreshed = setup()

    await apply_twilio_stream_status(
        session,
        passed,
        stream_sid="MZ-pinned",
        event="stream-started",
        error=None,
        provider_call_id="CA-first",
    )

    assert refreshed.provider_call_id == "CA-first"
    assert passed.provider_call_id is None
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("sequence_number", [True, False, 1.5, "2"])
async def test_call_status_rejects_non_integer_sequence(sequence_number):
    session, call, _ = setup()

    with pytest.raises(ValueError, match="nonnegative integer"):
        await apply_twilio_call_status(
            session, call, "ringing", sequence_number=sequence_number
        )

    session.get.assert_not_awaited()
    session.commit.assert_not_awaited()
