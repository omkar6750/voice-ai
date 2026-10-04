import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pipecat.frames.frames import (
    CancelFrame,
    EndFrame,
    ErrorFrame,
    InterruptionFrame,
    TTSStartedFrame,
)
from pipecat.observers.base_observer import FramePushed, ProcessorSetUp
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from voice_runtime.execution.local_observer import LocalErrorObserver, LocalLifecycleObserver
from voice_runtime.execution.local_trace import LocalRuntimeTrace


@pytest.mark.asyncio
async def test_selected_pipeline_lifecycle_frames_and_setup_are_safe(tmp_path):
    path = tmp_path / "trace.jsonl"
    trace = LocalRuntimeTrace(path, str(uuid4()))
    observer = LocalLifecycleObserver(trace)
    processor = FrameProcessor()

    for frame in (TTSStartedFrame(), CancelFrame(), InterruptionFrame(), EndFrame()):
        await observer.on_push_frame(SimpleNamespace(source=processor, frame=frame))
    await observer.on_processor_setup(
        ProcessorSetUp(processor=processor, started_at_ns=10, finished_at_ns=5_000_010)
    )
    trace.close()

    content = path.read_text()
    assert all(
        name in content
        for name in ("TTSStartedFrame", "CancelFrame", "InterruptionFrame", "EndFrame")
    )
    assert '"duration_ms":5.0' in content


@pytest.mark.asyncio
async def test_error_observer_records_safe_error_category_without_message(tmp_path):
    path = tmp_path / "trace.jsonl"
    trace = LocalRuntimeTrace(path, str(uuid4()))
    observer = LocalErrorObserver(trace)
    processor = FrameProcessor()
    message = "private transcript and provider exception"
    frame = ErrorFrame(error=message, processor=processor, exception=RuntimeError(message))
    await observer.on_push_frame(
        FramePushed(
            source=processor,
            destination=processor,
            frame=frame,
            direction=FrameDirection.DOWNSTREAM,
            timestamp=1,
        )
    )
    await asyncio.sleep(0.05)
    trace.close()

    content = path.read_text()
    assert '"event":"pipeline_error"' in content
    assert message not in content
    assert "RuntimeError" not in content


def test_slow_trace_sink_is_bounded_and_does_not_block_recording(tmp_path):
    import threading

    entered, release = threading.Event(), threading.Event()

    def slow_sink(_row):
        entered.set()
        release.wait(3)

    trace = LocalRuntimeTrace(tmp_path / "slow.jsonl", str(uuid4()), on_record=slow_sink)
    assert entered.wait(1)
    try:
        for _ in range(2000):
            trace.record("pipeline_frame", component="pipecat", frame_type="EndFrame")
        assert trace.dropped > 0
        assert trace._queue.qsize() <= 1024
    finally:
        release.set()
        trace.close()
    assert not trace._writer.is_alive()
