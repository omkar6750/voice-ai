"""Exercise the actual Pipecat Flows wrapper, not just the raw tool handler."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from pipecat.frames.frames import EndFrame
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.services.llm_service import FunctionCallParams
from voice_runtime.execution.native import NativePipelineHost, TracedFlowManager


def setup_flow():
    events = []
    host = NativePipelineHost("test-run", Path("unused"), SimpleNamespace())

    async def queue(frame):
        assert isinstance(frame, EndFrame)
        events.append("end_frame")

    host.worker = SimpleNamespace(queue_frame=AsyncMock(side_effect=queue), cancel=AsyncMock())
    host.tracker = Mock()
    host.tracker.tool_was_ended.return_value = False
    host.tracker.end_tool.side_effect = lambda *args, **kwargs: events.append("tool_finished")
    manager = object.__new__(TracedFlowManager)
    manager.tracker = host.tracker
    manager.bindings = {"end_call": {"version_id": "v1"}, "ordinary": {"version_id": "v2"}}
    manager.observer = SimpleNamespace(function_operations={}, llm_operation=None)
    manager._snapshot = {}
    manager._context_for_evidence = LLMContext([])
    manager._end_call_runner = host._finish_end_call
    return host, manager, events


def params(name, callback):
    return FunctionCallParams(
        function_name=name,
        tool_call_id="call-1",
        arguments={},
        llm=None,
        pipeline_worker=None,
        context=LLMContext([]),
        result_callback=callback,
    )


async def test_end_call_delivers_result_before_end_without_followup_inference():
    host, manager, events = setup_flow()

    async def result_callback(result, *, properties):
        assert result == {"status": "ok"}
        assert properties.run_llm is False
        host.worker.queue_frame.assert_not_awaited()
        events.append("tool_result")
        await properties.on_context_updated()

    execute = await manager._create_transition_func("end_call", host._handler("end_call"))
    assert await execute(params("end_call", result_callback)) == {"status": "ok"}
    assert events == ["tool_result", "tool_finished", "end_frame"]
    host.tracker.context_updated.assert_called_once()
    host.worker.cancel.assert_not_awaited()


async def test_repeated_end_call_records_results_but_queues_one_end_frame():
    host, manager, events = setup_flow()
    execute = await manager._create_transition_func("end_call", host._handler("end_call"))
    callback = AsyncMock()
    await execute(params("end_call", callback))
    await execute(params("end_call", callback))
    assert callback.await_count == 2
    assert events.count("end_frame") == 1
    assert host.tracker.diagnostic.call_count == 1


async def test_failed_end_call_result_does_not_request_shutdown():
    host, manager, _events = setup_flow()

    async def failed_handler(args, manager):
        return {"status": "error", "error": "cannot end"}

    callback = AsyncMock()
    execute = await manager._create_transition_func("end_call", failed_handler)
    result = await execute(params("end_call", callback))
    assert result["status"] == "error"
    assert callback.await_args.kwargs["properties"].run_llm is True
    host.worker.queue_frame.assert_not_awaited()


async def test_unrelated_tool_retains_its_original_followup_behavior():
    host, manager, _events = setup_flow()

    async def ordinary_handler(args, manager):
        return {"status": "ok", "data": 17}

    callback = AsyncMock()
    execute = await manager._create_transition_func("ordinary", ordinary_handler)
    assert await execute(params("ordinary", callback)) == {"status": "ok", "data": 17}
    assert callback.await_args.kwargs["properties"].run_llm is True
    host.worker.queue_frame.assert_not_awaited()


async def test_shutdown_queue_failure_is_visible_and_allows_cleanup_retry():
    host, manager, _events = setup_flow()
    host.worker.queue_frame.side_effect = RuntimeError("worker stopped")
    execute = await manager._create_transition_func("end_call", host._handler("end_call"))
    with pytest.raises(RuntimeError, match="worker stopped"):
        await execute(params("end_call", AsyncMock()))
    assert not host._end_frame_queued
    host.worker.queue_frame.side_effect = None
    await host._finish_end_call()
    assert host._end_frame_queued
