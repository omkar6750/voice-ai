"""Replay conversation tool broadcasts through the real voicemail branch seam."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from pipecat.frames.frames import (
    CancelFrame,
    EndFrame,
    FunctionCallFromLLM,
    FunctionCallInProgressFrame,
    FunctionCallResultFrame,
    FunctionCallResultProperties,
    FunctionCallsStartedFrame,
    LLMMessagesUpdateFrame,
    TranscriptionFrame,
)
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from voice_runtime.execution.observer import EvidenceObserver
from voice_runtime.execution.voicemail import AnswerDetection


@pytest.mark.parametrize("direction", [FrameDirection.UPSTREAM, FrameDirection.DOWNSTREAM])
async def test_conversation_tool_result_cannot_update_voicemail_context(monkeypatch, direction):
    detection = AnswerDetection(
        SimpleNamespace(), FrameProcessor(), timeout_seconds=5, provider="fake", model="fake"
    )
    detector = detection.detector
    classifier = detector._context_aggregator.assistant()
    conversation = LLMContextAggregatorPair(LLMContext([])).assistant()
    original_classifier_messages = list(detector._context.get_messages())
    callback = AsyncMock()
    tasks = []

    def create_task(coroutine, *args):
        task = asyncio.create_task(coroutine)
        tasks.append(task)
        return task

    for aggregator in (classifier, conversation):
        monkeypatch.setattr(aggregator, "create_task", create_task)
        monkeypatch.setattr(aggregator, "push_frame", AsyncMock())

    # Keep queue scheduling deterministic while exercising the installed
    # detector's fan-out and its real classifier assistant aggregator.
    monkeypatch.setattr(detector._pipelines[0], "queue_frame", AsyncMock())
    monkeypatch.setattr(
        detector._pipelines[1], "queue_frame", AsyncMock(side_effect=classifier.process_frame)
    )
    monkeypatch.setattr(detector, "push_frame", AsyncMock())
    progress = FunctionCallInProgressFrame("go_to_project_pitch", "call-1", {})
    result = FunctionCallResultFrame(
        "go_to_project_pitch",
        "call-1",
        {},
        {"status": "acknowledged"},
        properties=FunctionCallResultProperties(run_llm=False, on_context_updated=callback),
    )
    for frame in (progress, result):
        await detector.process_frame(frame, direction)
        await conversation.process_frame(frame, FrameDirection.DOWNSTREAM)
    await asyncio.gather(*tasks)

    callback.assert_awaited_once()
    assert detector._context.get_messages() == original_classifier_messages
    assert any(
        message.get("tool_call_id") == "call-1" for message in conversation._context.get_messages()
    )


@pytest.mark.parametrize("direction", [FrameDirection.UPSTREAM, FrameDirection.DOWNSTREAM])
async def test_conversation_prompt_updates_bypass_detector_but_transcripts_fan_out(
    monkeypatch, direction
):
    detection = AnswerDetection(
        SimpleNamespace(), FrameProcessor(), timeout_seconds=5, provider="fake", model="fake"
    )
    detector = detection.detector
    queues = [AsyncMock(), AsyncMock()]
    for branch, queue in zip(detector._pipelines, queues, strict=True):
        monkeypatch.setattr(branch, "queue_frame", queue)
    monkeypatch.setattr(detector, "push_frame", AsyncMock())
    prompt = LLMMessagesUpdateFrame([{"role": "system", "content": "Conversation prompt"}])
    await detector.process_frame(prompt, direction)
    detector.push_frame.assert_awaited_once_with(prompt, direction)
    for queue in queues:
        queue.assert_not_awaited()

    transcript = TranscriptionFrame("Hello", "caller", "2026-10-10T05:23:00Z")
    await detector.process_frame(transcript, FrameDirection.DOWNSTREAM)
    for queue in queues:
        queue.assert_awaited_once_with(transcript, FrameDirection.DOWNSTREAM)


@pytest.mark.parametrize("frame_type", [EndFrame, CancelFrame])
async def test_detector_still_fans_out_shutdown_frames(monkeypatch, frame_type):
    detection = AnswerDetection(
        SimpleNamespace(), FrameProcessor(), timeout_seconds=5, provider="fake", model="fake"
    )
    queues = [AsyncMock(), AsyncMock()]
    for branch, queue in zip(detection.detector._pipelines, queues, strict=True):
        monkeypatch.setattr(branch, "queue_frame", queue)
    frame = frame_type()
    await detection.detector.process_frame(frame, FrameDirection.DOWNSTREAM)
    for queue in queues:
        queue.assert_awaited_once_with(frame, FrameDirection.DOWNSTREAM)


async def test_llm_evidence_records_one_tool_call_for_bidirectional_broadcast():
    llm = object()
    observer = EvidenceObserver(
        Mock(),
        llm=llm,
        stt=None,
        tts=None,
        llm_provider="fake",
        stt_provider="fake",
        tts_provider="fake",
        llm_model="fake",
        stt_model="fake",
        tts_model="fake",
    )
    call = FunctionCallFromLLM("go_to_project_pitch", "call-1", {}, LLMContext([]))
    for direction in (FrameDirection.DOWNSTREAM, FrameDirection.UPSTREAM):
        await observer.on_push_frame(
            SimpleNamespace(
                source=llm, frame=FunctionCallsStartedFrame([call]), direction=direction
            )
        )
    assert observer.function_calls == [
        {"id": "call-1", "name": "go_to_project_pitch", "arguments": {}}
    ]
