"""Regression tests for browser-session runtime cleanup ownership."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from voice_api.services.browser_session_service import BrowserSessionContext


def make_context() -> BrowserSessionContext:
    context = BrowserSessionContext("session-id", "run-id", {})
    context.host = AsyncMock()
    context.request_handler = AsyncMock()
    return context


@pytest.mark.asyncio
async def test_repeated_close_runtime_closes_each_resource_once() -> None:
    context = make_context()

    await context.close_runtime()
    await context.close_runtime()

    context.host.close.assert_awaited_once()
    context.request_handler.close.assert_awaited_once()
    assert context.cleanup_complete


@pytest.mark.asyncio
async def test_concurrent_close_runtime_closes_each_resource_once() -> None:
    context = make_context()
    host_close_started = asyncio.Event()
    allow_host_close = asyncio.Event()

    async def close_host() -> None:
        host_close_started.set()
        await allow_host_close.wait()

    context.host.close.side_effect = close_host
    first = asyncio.create_task(context.close_runtime())
    await host_close_started.wait()

    second_started = asyncio.Event()

    async def close_from_second_caller() -> None:
        second_started.set()
        await context.close_runtime()

    second = asyncio.create_task(close_from_second_caller())
    await second_started.wait()
    allow_host_close.set()

    await asyncio.gather(first, second)

    context.host.close.assert_awaited_once()
    context.request_handler.close.assert_awaited_once()
    assert context.cleanup_complete


@pytest.mark.asyncio
async def test_host_close_failure_still_closes_handler_and_is_not_retried() -> None:
    context = make_context()
    host_error = RuntimeError("host close failed")
    context.host.close.side_effect = host_error

    with pytest.raises(RuntimeError) as exc_info:
        await context.close_runtime()

    assert exc_info.value is host_error
    context.host.close.assert_awaited_once()
    context.request_handler.close.assert_awaited_once()
    assert not context.cleanup_complete

    with pytest.raises(RuntimeError) as repeated:
        await context.close_runtime()
    assert repeated.value is host_error
    context.host.close.assert_awaited_once()
    context.request_handler.close.assert_awaited_once()
    assert not context.cleanup_complete


@pytest.mark.asyncio
async def test_first_close_error_is_propagated_after_both_closes_are_attempted() -> None:
    context = make_context()
    host_error = RuntimeError("host close failed")
    context.host.close.side_effect = host_error
    context.request_handler.close.side_effect = RuntimeError("handler close failed")

    with pytest.raises(RuntimeError) as exc_info:
        await context.close_runtime()

    assert exc_info.value is host_error
    context.host.close.assert_awaited_once()
    context.request_handler.close.assert_awaited_once()
    assert not context.cleanup_complete


@pytest.mark.asyncio
async def test_handler_close_failure_leaves_cleanup_incomplete() -> None:
    context = make_context()
    handler_error = RuntimeError("handler close failed")
    context.request_handler.close.side_effect = handler_error

    with pytest.raises(RuntimeError) as exc_info:
        await context.close_runtime()

    assert exc_info.value is handler_error
    context.host.close.assert_awaited_once()
    context.request_handler.close.assert_awaited_once()
    assert not context.cleanup_complete


@pytest.mark.asyncio
async def test_pipeline_finalizer_cleanup_does_not_deadlock_external_close() -> None:
    context = make_context()
    pipeline_started = asyncio.Event()

    async def run_pipeline() -> None:
        pipeline_started.set()
        try:
            await asyncio.Future()
        finally:
            await context.close_runtime()

    context.pipeline_task = asyncio.create_task(run_pipeline())
    await pipeline_started.wait()

    await asyncio.wait_for(context.close_runtime(), timeout=1)

    context.host.close.assert_awaited_once()
    context.request_handler.close.assert_awaited_once()
    assert context.cleanup_complete
