from __future__ import annotations

import asyncio
import base64
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pipecat.frames.frames import (
    CancelFrame,
    EndFrame,
    InputAudioRawFrame,
    InterruptionFrame,
    OutputAudioRawFrame,
)
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams
from starlette.websockets import WebSocketState
from voice_runtime.execution.termination import CallTermination
from voice_runtime.telephony.twilio_session import (
    ManagedTwilioSerializer,
    ManagedTwilioTransport,
    TwilioMediaSession,
)

STREAM = "MZ" + "c" * 32


class Sent(list):
    def __init__(self):
        super().__init__()
        self.mark_sent = asyncio.Event()

    def append(self, message):
        super().append(message)
        if message["event"] == "mark":
            self.mark_sent.set()


def setup(*, timeout=0.05):
    termination = CallTermination()
    sent = Sent()

    async def send(message):
        sent.append(message)

    rest = SimpleNamespace(
        complete=AsyncMock(return_value="completed"),
        status=AsyncMock(return_value="completed"),
        aclose=AsyncMock(),
    )
    session = TwilioMediaSession(STREAM, termination, send, rest, playback_timeout_secs=timeout)
    return session, termination, sent, rest


async def media(session):
    await session.send_payload(
        {"event": "media", "streamSid": STREAM, "media": {"payload": "AA=="}}
    )


async def wait_mark(sent):
    async with asyncio.timeout(1):
        await sent.mark_sent.wait()
    return next(p["mark"]["name"] for p in sent if p["event"] == "mark")


@pytest.mark.asyncio
async def test_final_mark_precedes_one_hangup_and_verified_release():
    session, termination, sent, rest = setup()
    await media(session)
    termination.request("terminal_completed", graceful=True)
    first = asyncio.create_task(session.close(graceful=True))
    second = asyncio.create_task(session.close(graceful=True))
    mark = await wait_mark(sent)
    assert rest.complete.await_count == 0
    session.acknowledge("stale-mark")
    assert not first.done()
    session.acknowledge(mark)
    await asyncio.gather(first, second)
    await session.close()
    rest.complete.assert_awaited_once()
    rest.status.assert_awaited_once()
    rest.aclose.assert_awaited_once()
    assert termination.summary.playback_status == "drained"
    assert termination.summary.playback_source == "twilio_mark"
    assert termination.summary.cleanup_status == "confirmed"
    termination.pipeline_finished()
    assert termination.summary.execution_status == "completed"


@pytest.mark.asyncio
async def test_clear_returned_mark_never_proves_playback():
    session, termination, sent, rest = setup()
    await media(session)
    termination.request("agent_hangup", graceful=True)
    task = asyncio.create_task(session.close(graceful=True))
    mark = await wait_mark(sent)
    await session.send_payload({"event": "clear", "streamSid": STREAM})
    session.acknowledge(mark)
    await task
    assert termination.summary.playback_status == "interrupted"
    assert termination.summary.playback_source != "twilio_mark"
    assert termination.summary.cause == "cancelled"
    rest.complete.assert_awaited_once()


@pytest.mark.asyncio
async def test_mark_timeout_is_failed_but_still_attempts_release():
    session, termination, _, rest = setup(timeout=0.01)
    await media(session)
    termination.request("agent_hangup", graceful=True)
    await session.close(graceful=True)
    termination.pipeline_finished()
    assert termination.summary.cause == "drain_timeout"
    assert termination.summary.execution_status == "failed"
    assert termination.summary.cleanup_status == "confirmed"
    assert any(d["code"] == "twilio_playback_timeout" for d in session.diagnostics)
    rest.complete.assert_awaited_once()


@pytest.mark.asyncio
async def test_no_audio_does_not_invent_playback_confirmation():
    session, termination, sent, _ = setup()
    await session.close(graceful=True)
    assert sent == []
    assert termination.summary.playback_status == "unknown"


@pytest.mark.asyncio
async def test_external_disconnect_interrupts_pending_mark_not_caller_disinterest():
    session, termination, sent, rest = setup()
    await media(session)
    termination.request("terminal_completed", graceful=True)
    task = asyncio.create_task(session.close(graceful=True))
    await wait_mark(sent)
    session.disconnected()
    await task
    assert termination.summary.cause == "disconnect_unknown"
    assert termination.summary.playback_status == "interrupted"
    rest.complete.assert_awaited_once()


@pytest.mark.asyncio
async def test_own_hangup_disconnect_does_not_override_agent_outcome():
    session, termination, _, rest = setup()
    termination.request("agent_hangup", graceful=True)

    async def complete():
        session.disconnected()
        assert await session()

    rest.complete.side_effect = complete
    await session.close(graceful=True)
    assert termination.summary.cause == "agent_hangup"


@pytest.mark.asyncio
async def test_uncertain_post_is_read_back_not_retried():
    session, termination, _, rest = setup()
    rest.complete.side_effect = TimeoutError("secret private error")
    await session.close()
    rest.complete.assert_awaited_once()
    rest.status.assert_awaited_once()
    assert termination.summary.cleanup_status == "confirmed"
    assert "secret" not in str(session.diagnostics)


@pytest.mark.parametrize("status", ["in-progress", None])
@pytest.mark.asyncio
async def test_nonterminal_or_unreadable_rest_does_not_confirm_release(status):
    session, termination, _, rest = setup()
    rest.status.return_value = status
    if status is None:
        rest.status.side_effect = RuntimeError("private response body")
    await session.close()
    assert termination.summary.cleanup_status == "uncertain"
    assert any(d["code"] == "twilio_hangup_uncertain" for d in session.diagnostics)
    assert "private" not in str(session.diagnostics)


@pytest.mark.asyncio
async def test_canceled_waiter_cannot_orphan_or_duplicate_post():
    session, _, _, rest = setup()
    entered, release = asyncio.Event(), asyncio.Event()

    async def complete():
        entered.set()
        await release.wait()

    rest.complete.side_effect = complete
    task = asyncio.create_task(session.close())
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    release.set()
    await session.close()
    rest.complete.assert_awaited_once()
    rest.status.assert_awaited_once()


@pytest.mark.asyncio
async def test_immediate_close_escalates_pending_graceful_drain():
    session, termination, sent, _ = setup()
    await media(session)
    termination.request("terminal_completed", graceful=True)
    first = asyncio.create_task(session.close(graceful=True))
    await wait_mark(sent)
    await session.close()
    await first
    assert termination.summary.cause == "cancelled"


@pytest.mark.asyncio
async def test_media_is_not_appended_behind_final_mark():
    session, _, sent, _ = setup()
    await media(session)
    task = asyncio.create_task(session.close(graceful=True))
    mark = await wait_mark(sent)
    await media(session)
    assert sum(p["event"] == "media" for p in sent) == 1
    session.acknowledge(mark)
    await task


@pytest.mark.asyncio
async def test_send_failure_is_sanitized_and_changes_cause():
    session, termination, _, _ = setup()
    session._send = AsyncMock(side_effect=RuntimeError("secret body"))
    with pytest.raises(RuntimeError, match="Twilio stream write failed") as caught:
        await media(session)
    assert "secret" not in str(caught.value)
    assert not await session()
    assert termination.summary.cause == "network_failure"


@pytest.mark.asyncio
async def test_managed_serializer_retains_pipecat_audio_codec_and_clear():
    session, _, sent, _ = setup()
    serializer = ManagedTwilioSerializer(session, sample_rate=8000)
    await serializer.setup(SimpleNamespace(audio_in_sample_rate=8000))
    await serializer.serialize(
        OutputAudioRawFrame(audio=b"\0\0" * 160, sample_rate=8000, num_channels=1)
    )
    assert sent[0]["event"] == "media"
    payload = base64.b64decode(sent[0]["media"]["payload"])
    assert len(payload) == 160  # 20ms raw mu-law, no WAV header.
    frame = await serializer.deserialize(json.dumps(sent[0]))
    assert isinstance(frame, InputAudioRawFrame)
    assert frame.sample_rate == 8000 and len(frame.audio) == 320
    await serializer.serialize(InterruptionFrame())
    assert sent[-1] == {"event": "clear", "streamSid": STREAM}


@pytest.mark.parametrize(
    "data", ["not json", "[]", json.dumps({"event": "stop", "streamSid": "other"})]
)
@pytest.mark.asyncio
async def test_invalid_inbound_protocol_fails_closed(data):
    session, termination, _, _ = setup()
    serializer = ManagedTwilioSerializer(session, sample_rate=8000)
    with pytest.raises(ValueError):
        await serializer.deserialize(data)
    assert termination.summary.cause == "network_failure"
    assert not await session()


@pytest.mark.asyncio
async def test_real_pipecat_reader_survives_input_end_and_receives_final_mark():
    session, termination, sent, rest = setup()
    queue = asyncio.Queue()
    ws = SimpleNamespace(
        headers={},
        client_state=WebSocketState.CONNECTED,
        application_state=WebSocketState.CONNECTED,
        receive=queue.get,
        close=AsyncMock(),
    )
    serializer = ManagedTwilioSerializer(session, sample_rate=8000)
    transport = ManagedTwilioTransport(
        ws, FastAPIWebsocketParams(serializer=serializer, allowed_origins=[])
    )
    reader = asyncio.create_task(transport.input()._receive_messages())
    await media(session)
    termination.request("terminal_completed", graceful=True)
    try:
        with (
            patch.object(transport.input(), "_cancel_audio_task", new=AsyncMock()),
            patch("pipecat.transports.base_output.BaseOutputTransport.stop", new=AsyncMock()),
        ):
            await transport.input().stop(EndFrame())
            assert not reader.done() and not transport._client.is_closing
            task = asyncio.create_task(transport.output().stop(EndFrame()))
            mark = await wait_mark(sent)
            rest.complete.assert_not_awaited()
            await queue.put(
                {
                    "type": "websocket.receive",
                    "text": json.dumps(
                        {"event": "mark", "streamSid": STREAM, "mark": {"name": mark}}
                    ),
                }
            )
            await asyncio.wait_for(task, 1)
        assert termination.summary.playback_source == "twilio_mark"
        rest.complete.assert_awaited_once()
    finally:
        reader.cancel()
        await asyncio.gather(reader, return_exceptions=True)


@pytest.mark.asyncio
async def test_cancel_serializer_and_finally_share_one_close_owner():
    session, _, _, rest = setup()
    serializer = ManagedTwilioSerializer(session, sample_rate=8000)
    await serializer.serialize(CancelFrame())
    await session.close()
    rest.complete.assert_awaited_once()
