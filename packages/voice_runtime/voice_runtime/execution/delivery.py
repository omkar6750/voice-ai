"""One replay-safe uploader plus independent disk-health monitoring per live call."""

import asyncio
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Any

from voice_runtime.contracts.evidence import EvidenceRecordValidationError
from voice_runtime.diagnostics import diagnostic_dict
from voice_runtime.execution.evidence_client import EvidenceDeliveryError
from voice_runtime.execution.spool import BatchIngestor, DurableSpool


async def stream_evidence(
    spool: DurableSpool,
    ingestor: BatchIngestor,
    *,
    poll_seconds: float = 0.1,
    retry_seconds: float = 2,
) -> None:
    if poll_seconds <= 0 or retry_seconds <= 0:
        raise ValueError("Evidence delivery intervals must be positive")

    async def upload():
        while True:
            try:
                count = await spool.deliver_once(ingestor)
            except EvidenceDeliveryError as exc:
                if not exc.retryable:
                    raise
                # Only idempotent evidence batches retry, never calls or action tools.
                await asyncio.sleep(retry_seconds)
            else:
                await asyncio.sleep(0 if count else poll_seconds)

    async def health():
        while True:
            spool.check()
            await asyncio.sleep(poll_seconds)

    # A blocked HTTP request must not hide a writer/quota failure.
    async with asyncio.TaskGroup() as tasks:
        tasks.create_task(upload())
        tasks.create_task(health())


@dataclass(frozen=True)
class EvidenceFinalization:
    incomplete: bool
    diagnostic: dict[str, Any] | None


async def supervise_execution(operation: Awaitable[Any], delivery_task: asyncio.Task) -> Any:
    """Fail live execution promptly if its evidence writer/uploader becomes unhealthy."""
    operation_task = asyncio.ensure_future(operation)
    done, _ = await asyncio.wait(
        (operation_task, delivery_task), return_when=asyncio.FIRST_COMPLETED
    )
    if operation_task in done:
        return await operation_task
    if delivery_task in done:
        operation_task.cancel()
        await asyncio.gather(operation_task, return_exceptions=True)
        try:
            await delivery_task
        except BaseException as exc:
            failure = _find_delivery_error(exc)
            if failure is not None:
                raise failure from None
            raise
        raise RuntimeError("Evidence delivery stopped unexpectedly")
    return await operation_task


async def finalize_evidence(
    spool: DurableSpool,
    ingestor: BatchIngestor,
    delivery_task: asyncio.Task | None,
    *,
    timeout_seconds: float = 15,
) -> EvidenceFinalization:
    """Stop the streaming uploader, drain once, and retain/report anything unacknowledged."""
    failure: EvidenceDeliveryError | None = None
    if delivery_task is not None:
        delivery_task.cancel()
        result = await asyncio.gather(delivery_task, return_exceptions=True)
        if isinstance(result[0], BaseException) and not isinstance(
            result[0], asyncio.CancelledError
        ):
            failure = _find_delivery_error(result[0])

    incomplete = failure is not None
    try:
        async with asyncio.timeout(timeout_seconds):
            await spool.flush()
            if not incomplete:
                while await spool.deliver_once(ingestor):
                    pass
    except Exception as exc:
        incomplete = True
        failure = failure or _find_delivery_error(exc)
    try:
        await spool.close()
    except Exception as exc:
        incomplete = True
        failure = failure or _find_delivery_error(exc)

    if not incomplete:
        return EvidenceFinalization(incomplete=False, diagnostic=None)
    metadata: dict[str, Any] = {}
    if failure is not None:
        metadata["failure_kind"] = failure.failure_kind or "delivery_failed"
        if failure.event_index is not None:
            metadata["event_index"] = failure.event_index
        if failure.event_kind is not None:
            metadata["event_kind"] = failure.event_kind
        if failure.validation_location is not None:
            metadata["validation_location"] = failure.validation_location
    return EvidenceFinalization(
        incomplete=True,
        diagnostic=diagnostic_dict(
            severity="error",
            category="evidence_delivery",
            source="evidence",
            code=(failure.failure_kind if failure else None) or "evidence_incomplete",
            message="Evidence is incomplete; durable spool records remain available for replay",
            retryable=failure.retryable if failure else False,
            metadata=metadata,
        ),
    )


def _find_delivery_error(error: BaseException) -> EvidenceDeliveryError | None:
    if isinstance(error, EvidenceDeliveryError):
        return error
    if isinstance(error, EvidenceRecordValidationError):
        return EvidenceDeliveryError(
            retryable=False,
            failure_kind="invalid_record",
            event_kind=error.event_kind,
            validation_location=error.validation_location,
        )
    nested = getattr(error, "exceptions", ())
    for item in nested:
        result = _find_delivery_error(item)
        if result is not None:
            return result
    cause = error.__cause__ or error.__context__
    if cause is not None:
        return _find_delivery_error(cause)
    return None
