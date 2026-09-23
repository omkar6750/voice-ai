"""One replay-safe uploader plus independent disk-health monitoring per live call."""

import asyncio

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
