"""Native host cleanup runs once and reports uncertainty without masking failures."""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from voice_runtime.execution.native import NativePipelineHost


def make_host():
    host = NativePipelineHost("run", Path("unused"), SimpleNamespace())
    host.tracker = Mock()
    host.observer = Mock()
    host.capture = Mock()
    return host


async def test_repeated_close_runs_cleanup_once():
    host = make_host()

    await host.close()
    await host.close()

    host.tracker.end_visit.assert_called_once_with("interrupted")
    host.tracker.end_exchange.assert_called_once_with("interrupted")
    host.observer.close.assert_called_once()
    host.capture.close.assert_called_once()
    assert host.termination.summary.cleanup_status == "unknown"


async def test_concurrent_close_waits_for_single_cleanup_attempt():
    host = make_host()
    started = asyncio.Event()
    release = asyncio.Event()

    async def cancel_worker():
        started.set()
        await release.wait()

    host.worker = SimpleNamespace(cancel=AsyncMock(side_effect=cancel_worker))
    first = asyncio.create_task(host.close())
    await started.wait()
    second = asyncio.create_task(host.close())
    await asyncio.sleep(0)
    release.set()
    await asyncio.gather(first, second)

    host.worker.cancel.assert_awaited_once()
    host.observer.close.assert_called_once()
    host.capture.close.assert_called_once()


async def test_observer_failure_does_not_skip_capture_and_repeats_same_error():
    host = make_host()
    error = RuntimeError("observer close failed")
    host.observer.close.side_effect = error

    with pytest.raises(RuntimeError, match="observer close failed") as first:
        await host.close()
    with pytest.raises(RuntimeError, match="observer close failed") as second:
        await host.close()

    assert first.value is error
    assert second.value is error
    host.capture.close.assert_called_once()
    assert host.termination.summary.cleanup_status == "uncertain"


async def test_completed_terminal_call_stays_completed_when_cleanup_is_uncertain():
    host = make_host()
    host.termination.request("terminal_completed", graceful=True)
    host.termination.pipeline_finished()
    host.observer.close.side_effect = RuntimeError("observer close failed")

    with pytest.raises(RuntimeError, match="observer close failed"):
        await host.close()

    assert host.termination.summary.execution_status == "completed"
    assert host.termination.summary.cleanup_status == "uncertain"
    host.tracker.end_visit.assert_called_once_with("completed")
    host.tracker.end_exchange.assert_called_once_with("completed")
    host.capture.close.assert_called_once()


async def test_tracker_error_does_not_skip_exchange_or_resource_cleanup():
    host = make_host()
    error = RuntimeError("visit finalization failed")
    host.tracker.end_visit.side_effect = error

    with pytest.raises(RuntimeError, match="visit finalization failed") as raised:
        await host.close()

    assert raised.value is error
    host.tracker.end_exchange.assert_called_once_with("interrupted")
    host.observer.close.assert_called_once()
    host.capture.close.assert_called_once()
    assert host.termination.summary.cleanup_status == "uncertain"


async def test_cancellation_is_reraised_after_resource_cleanup():
    host = make_host()
    host.runner_task = asyncio.create_task(asyncio.Event().wait())
    await asyncio.sleep(0)
    closing = asyncio.create_task(host.close())
    await asyncio.sleep(0)
    closing.cancel()

    result = await asyncio.gather(closing, return_exceptions=True)

    assert isinstance(result[0], asyncio.CancelledError)
    assert host.termination.summary.cause == "cancelled"
    host.observer.close.assert_called_once()
    host.capture.close.assert_called_once()
    with pytest.raises(asyncio.CancelledError):
        await host.close()


async def test_pipeline_error_survives_secondary_cleanup_failure():
    host = make_host()
    pipeline_error = RuntimeError("pipeline failed")
    host.runner_task = asyncio.create_task(_fail(pipeline_error))
    host.observer.close.side_effect = RuntimeError("observer close failed")

    with pytest.raises(RuntimeError, match="pipeline failed") as first:
        await host.close()
    with pytest.raises(RuntimeError, match="pipeline failed") as repeated:
        await host.close()

    assert first.value is pipeline_error
    assert repeated.value is pipeline_error
    assert host.termination.summary.cause == "pipeline_failure"
    assert host.termination.summary.cleanup_status == "uncertain"
    host.tracker.end_visit.assert_called_once_with("failed")
    host.tracker.end_exchange.assert_called_once_with("failed")
    host.capture.close.assert_called_once()


async def _fail(error):
    raise error
