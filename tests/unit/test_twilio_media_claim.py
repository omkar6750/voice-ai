from unittest.mock import AsyncMock
from unittest.mock import call as mock_call

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from voice_api.models import Call, Run
from voice_api.services.call_service import claim_twilio_media


def setup(*, call_status="queued", run_status="queued", metadata=None, **overrides):
    run_link = overrides.pop("run_id", "run-1")
    provider = overrides.pop("provider", "twilio")
    call = Call(
        id="call-1",
        run_id=run_link,
        provider=provider,
        provider_call_id=None,
        status=call_status,
        provider_metadata=metadata or {},
        **overrides,
    )
    run = Run(
        id="run-1",
        status=run_status,
        resolved_config={"agent": {"prompt": "hello"}},
    )
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
async def test_media_claim_locks_call_then_run_and_commits_once():
    session, call, run = setup()

    result = await claim_twilio_media(
        session,
        call_id=call.id,
        run_id=run.id,
        provider_call_id="CA-provider",
        stream_sid="MZ-stream",
    )

    assert result == run.resolved_config
    assert run.status == "running"
    assert run.claim_token
    assert run.claimed_at is not None
    assert run.lease_expires_at is not None
    assert run.started_at is not None
    assert call.provider_call_id == "CA-provider"
    assert call.status == "active"
    assert call.provider_metadata["stream_sid"] == "MZ-stream"
    assert call.provider_metadata["stream_status"] == "started"
    assert session.get.await_args_list == [
        mock_call(Call, call.id, with_for_update=True, populate_existing=True),
        mock_call(Run, run.id, with_for_update=True, populate_existing=True),
    ]
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("call_status", "run_status", "metadata", "provider", "run_link", "snapshot"),
    [
        ("completed", "queued", {}, "twilio", "run-1", {"x": 1}),
        ("queued", "failed", {}, "twilio", "run-1", {"x": 1}),
        ("queued", "running", {}, "twilio", "run-1", {"x": 1}),
        ("queued", "queued", {"stream_sid": "MZ-other"}, "twilio", "run-1", {"x": 1}),
        ("queued", "queued", {}, "sim7600", "run-1", {"x": 1}),
        ("queued", "queued", {}, "twilio", "different-run", {"x": 1}),
        ("queued", "queued", {}, "twilio", "run-1", None),
    ],
)
async def test_invalid_or_duplicate_handshake_does_not_claim(
    call_status, run_status, metadata, provider, run_link, snapshot
):
    session, call, run = setup(
        call_status=call_status,
        run_status=run_status,
        metadata=metadata,
        provider=provider,
        run_id=run_link,
    )
    run.resolved_config = snapshot

    result = await claim_twilio_media(
        session,
        call_id=call.id,
        run_id="run-1",
        provider_call_id="CA-provider",
        stream_sid="MZ-stream",
    )

    assert result is None
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_pinned_call_identity_mismatch_does_not_claim():
    session, call, _ = setup()
    call.provider_call_id = "CA-original"

    result = await claim_twilio_media(
        session,
        call_id=call.id,
        run_id="run-1",
        provider_call_id="CA-other",
        stream_sid="MZ-stream",
    )

    assert result is None
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_call_or_run_does_not_claim():
    session, call, _ = setup()
    session.get.side_effect = [None]

    result = await claim_twilio_media(
        session,
        call_id=call.id,
        run_id="run-1",
        provider_call_id="CA-provider",
        stream_sid="MZ-stream",
    )

    assert result is None
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_terminal_stream_marker_prevents_claim():
    session, call, _ = setup(metadata={"stream_status": "stopped"})

    result = await claim_twilio_media(
        session,
        call_id=call.id,
        run_id="run-1",
        provider_call_id="CA-provider",
        stream_sid="MZ-stream",
    )

    assert result is None
    session.commit.assert_not_awaited()
