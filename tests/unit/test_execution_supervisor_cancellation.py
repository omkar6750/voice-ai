import asyncio

import pytest
from voice_runtime.execution.delivery import supervise_execution


async def test_supervisor_cancellation_joins_operation_and_leaves_delivery_owned():
    operation_started = asyncio.Event()
    cleanup_started = asyncio.Event()
    allow_cleanup = asyncio.Event()
    operation_finished = asyncio.Event()

    async def operation():
        operation_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleanup_started.set()
            await allow_cleanup.wait()
            operation_finished.set()

    async def delivery():
        await asyncio.Event().wait()

    delivery_task = asyncio.create_task(delivery())
    supervisor = asyncio.create_task(supervise_execution(operation(), delivery_task))
    try:
        await operation_started.wait()
        supervisor.cancel()
        await cleanup_started.wait()

        assert not supervisor.done()
        assert not operation_finished.is_set()
        assert not delivery_task.done()

        allow_cleanup.set()
        with pytest.raises(asyncio.CancelledError):
            await supervisor

        assert operation_finished.is_set()
        assert not delivery_task.done()
    finally:
        allow_cleanup.set()
        delivery_task.cancel()
        await asyncio.gather(supervisor, delivery_task, return_exceptions=True)


async def test_supervisor_returns_operation_result_without_stopping_delivery():
    async def operation():
        return "completed"

    async def delivery():
        await asyncio.Event().wait()

    delivery_task = asyncio.create_task(delivery())
    try:
        assert await supervise_execution(operation(), delivery_task) == "completed"
        assert not delivery_task.done()
    finally:
        delivery_task.cancel()
        await asyncio.gather(delivery_task, return_exceptions=True)
