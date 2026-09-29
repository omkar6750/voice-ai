from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from voice_api.models import Call, Run
from voice_api.services.call_service import apply_twilio_call_status


def setup(call_status="queued", run_status="running", metadata=None, error=None):
    call = Call(
        id="call-1",
        run_id="run-1",
        contact_id="contact-1",
        agent_version_id="agent-1",
        provider="twilio",
        status=call_status,
        provider_metadata=metadata or {},
    )
    run = Run(id="run-1", status=run_status, error=error)
    session = AsyncMock(spec=AsyncSession)

    async def get(model, identity, **kwargs):
        if model is Call:
            return call
        if model is Run:
            return run
        return None

    session.get.side_effect = get
    return session, call, run


@pytest.mark.asyncio
async def test_older_and_duplicate_sequence_numbers_are_ignored():
    session, call, _ = setup(
        "active", metadata={"twilio_sequence_number": 5, "twilio_status": "in-progress"}
    )

    await apply_twilio_call_status(session, call, "ringing", sequence_number=4)
    await apply_twilio_call_status(session, call, "in-progress", sequence_number=5)

    assert call.status == "active"
    assert call.provider_metadata["twilio_sequence_number"] == 5
    assert session.commit.await_count == 0


@pytest.mark.asyncio
async def test_new_sequence_is_saved_and_raw_status_is_normalized():
    session, call, _ = setup()

    await apply_twilio_call_status(session, call, "RINGING", sequence_number=8)

    assert call.status == "ringing"
    assert call.provider_metadata["twilio_status"] == "ringing"
    assert call.provider_metadata["twilio_raw_status"] == "ringing"
    assert call.provider_metadata["twilio_sequence_number"] == 8


@pytest.mark.asyncio
async def test_status_without_sequence_cannot_regress_call():
    session, call, _ = setup("active")

    await apply_twilio_call_status(session, call, "ringing")

    assert call.status == "active"
    assert session.commit.await_count == 0


@pytest.mark.asyncio
async def test_terminal_call_does_not_regress_or_change_terminal_kind():
    session, call, _ = setup("completed")

    await apply_twilio_call_status(session, call, "active", sequence_number=99)
    await apply_twilio_call_status(session, call, "failed", sequence_number=100)

    assert call.status == "completed"
    assert session.commit.await_count == 0


@pytest.mark.asyncio
async def test_queued_run_fails_on_provider_failure_and_keeps_prior_error():
    session, call, run = setup("queued", "claimed", error="existing runtime error")

    await apply_twilio_call_status(session, call, "no-answer", sequence_number=1)

    assert call.status == "failed"
    assert run.status == "failed"
    assert run.error == "existing runtime error"
    assert call.provider_metadata["twilio_status"] == "no-answer"


@pytest.mark.asyncio
async def test_provider_completion_does_not_complete_run():
    session, call, run = setup("active", "running", {"stream_sid": "MZ1"})

    await apply_twilio_call_status(session, call, "completed", sequence_number=2)

    assert call.status == "completed"
    assert run.status == "running"


@pytest.mark.asyncio
async def test_unknown_or_missing_status_is_ignored():
    session, call, _ = setup()

    await apply_twilio_call_status(session, call, "mystery")
    await apply_twilio_call_status(session, call, None)

    assert call.status == "queued"
    assert session.commit.await_count == 0


@pytest.mark.asyncio
async def test_negative_sequence_is_rejected():
    session, call, _ = setup()

    with pytest.raises(ValueError, match="nonnegative"):
        await apply_twilio_call_status(session, call, "ringing", sequence_number=-1)


@pytest.mark.asyncio
async def test_status_update_requests_refreshing_row_lock():
    session, call, _ = setup()

    await apply_twilio_call_status(session, call, "ringing", sequence_number=1)

    session.get.assert_any_await(Call, call.id, with_for_update=True, populate_existing=True)
