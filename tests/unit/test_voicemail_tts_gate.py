"""Replay interrupted speech through the real answer-detection gate."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from pipecat.clocks.system_clock import SystemClock
from pipecat.frames.frames import (
    CancelFrame,
    EndFrame,
    InterruptionFrame,
    TTSAudioRawFrame,
    TTSStartedFrame,
    TTSStoppedFrame,
    TTSTextFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor, FrameProcessorSetup
from pipecat.utils.asyncio.task_manager import TaskManager
from voice_runtime.execution.voicemail import AnswerDetection


def speech(context_id):
    return [
        TTSStartedFrame(context_id=context_id),
        TTSTextFrame("Greeting", aggregated_by="sentence", context_id=context_id),
        TTSAudioRawFrame(b"\x00\x00" * 160, 16000, 1, context_id=context_id),
        TTSStoppedFrame(context_id=context_id),
    ]


@pytest.fixture
async def gate():
    detection = AnswerDetection(
        SimpleNamespace(), FrameProcessor(), timeout_seconds=5, provider="fake", model="fake"
    )
    processor = detection.detector.gate()
    processor.push_frame = AsyncMock()
    await processor.setup(
        FrameProcessorSetup(clock=SystemClock(), task_manager=TaskManager(), pipeline_worker=Mock())
    )
    await asyncio.sleep(0)
    yield processor
    await processor.cleanup()


async def feed(gate, frames):
    for frame in frames:
        await gate.process_frame(frame, FrameDirection.DOWNSTREAM)


async def open_gate(gate):
    await gate._conversation_notifier.notify()
    await asyncio.wait_for(asyncio.shield(gate._conversation_task), timeout=2)


def delivered(gate):
    return [call.args[0] for call in gate.push_frame.await_args_list]


async def test_interruption_before_verdict_discards_old_audio_and_text(gate):
    old, fresh = speech("old"), speech("fresh")
    await feed(gate, old)
    interruption = InterruptionFrame()
    await feed(gate, [interruption])
    # Simulate late provider output from the canceled synthesis context.
    await feed(gate, speech("old"))
    await feed(gate, fresh)
    await open_gate(gate)
    assert delivered(gate) == [interruption, *fresh]


async def test_interruption_during_release_stops_remaining_old_frames(gate):
    old, fresh = speech("old"), speech("fresh")
    await feed(gate, old)
    interruption = InterruptionFrame()
    output = []

    async def push(frame, direction):
        output.append(frame)
        if frame is old[0]:
            await gate.process_frame(interruption, direction)

    gate.push_frame.side_effect = push
    await open_gate(gate)
    await feed(gate, speech("old"))
    await feed(gate, fresh)
    assert output == [old[0], interruption, *fresh]


async def test_uninterrupted_release_preserves_order(gate):
    frames = speech("normal")
    await feed(gate, frames)
    await open_gate(gate)
    assert delivered(gate) == frames


async def test_new_response_arriving_during_interrupted_release_is_preserved(gate):
    old, fresh = speech("old"), speech("fresh")
    await feed(gate, old)
    interruption = InterruptionFrame()
    output = []

    async def push(frame, direction):
        output.append(frame)
        if frame is old[0]:
            await gate.process_frame(interruption, direction)
            await feed(gate, fresh)

    gate.push_frame.side_effect = push
    await open_gate(gate)
    assert output == [old[0], interruption, *fresh]


@pytest.mark.parametrize("direction", [FrameDirection.DOWNSTREAM, FrameDirection.UPSTREAM])
async def test_open_gate_rejects_late_canceled_context_but_allows_new_response(gate, direction):
    await open_gate(gate)
    old = speech("old")
    await feed(gate, old)
    interruption = InterruptionFrame()
    await gate.process_frame(interruption, direction)
    await feed(gate, speech("old"))
    fresh = speech("fresh")
    await feed(gate, fresh)
    assert delivered(gate) == [*old, interruption, *fresh]


async def test_interruption_discards_frames_without_context_ids(gate):
    await feed(gate, speech(None))
    interruption = InterruptionFrame()
    await feed(gate, [interruption])
    await open_gate(gate)
    assert delivered(gate) == [interruption]


@pytest.mark.parametrize("frame_type", [EndFrame, CancelFrame])
async def test_shutdown_cannot_release_held_speech(gate, frame_type):
    await feed(gate, speech("old"))
    ending = frame_type()
    await feed(gate, [ending])
    await open_gate(gate)
    assert delivered(gate) == [ending]


async def test_voicemail_verdict_discards_speech(gate):
    await feed(gate, speech("old"))
    await gate._voicemail_notifier.notify()
    await asyncio.wait_for(asyncio.shield(gate._voicemail_task), timeout=2)
    assert delivered(gate) == []
