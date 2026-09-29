"""Saved call controls must reach Pipecat's user-turn aggregator."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from pipecat.frames.frames import EndFrame
from voice_runtime.execution.native import NativePipelineHost, build_user_aggregator_params


def test_interruptions_and_idle_timeout_are_applied_to_turn_settings():
    vad = object()
    enabled = build_user_aggregator_params(
        {"call_limits": {"interruptions_enabled": True, "idle_timeout_secs": 35}}, vad
    )
    assert enabled.vad_analyzer is vad
    assert enabled.user_idle_timeout == 35
    assert enabled.user_turn_strategies is None

    disabled = build_user_aggregator_params(
        {"call_limits": {"interruptions_enabled": False, "idle_timeout_secs": 12}}, vad
    )
    assert disabled.user_idle_timeout == 12
    assert all(
        not strategy._enable_interruptions for strategy in disabled.user_turn_strategies.start
    )


async def test_one_idle_reprompt_then_bounded_call_end():
    host = NativePipelineHost("test-run", Path("unused"), SimpleNamespace())
    host.worker = SimpleNamespace(queue_frame=AsyncMock(), cancel=AsyncMock())
    host.tracker = Mock()

    await host._handle_user_idle()
    assert host.worker.queue_frame.await_count == 1
    assert host.worker.queue_frame.await_args.args[0].text == "Are you still there?"
    assert host.worker.cancel.await_count == 0

    await host._handle_user_idle()
    await host._end_task
    assert host.worker.cancel.await_count == 1
    assert host.tracker.diagnostic.call_args.kwargs["code"] == "caller_idle_timeout"


async def test_end_call_intent_does_not_queue_end_before_result_delivery():
    host = NativePipelineHost("test-run", Path("unused"), SimpleNamespace())
    host.worker = SimpleNamespace(queue_frame=AsyncMock(), cancel=AsyncMock())
    host.tracker = Mock()

    handler = host._handler("end_call")
    assert await handler({}, None) == {"status": "ok"}
    assert await handler({}, None) == {"status": "ok"}
    host.worker.queue_frame.assert_not_awaited()
    await host._finish_end_call()
    await host._finish_end_call()
    assert host.worker.queue_frame.await_count == 1
    assert isinstance(host.worker.queue_frame.await_args.args[0], EndFrame)
    host.worker.cancel.assert_not_awaited()
