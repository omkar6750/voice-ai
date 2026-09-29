"""One claimed call: fence before effects, renew ownership, always release transport first."""

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Protocol
from uuid import uuid4

import httpx
from loguru import logger

from voice_runtime.diagnostics import diagnostic_dict, exception_diagnostic
from voice_runtime.execution.delivery import stream_evidence
from voice_runtime.execution.evidence_client import ApiEvidenceIngestor
from voice_runtime.execution.exchange import ExchangeTracker
from voice_runtime.execution.spool import BatchIngestor, DurableSpool


class CallDriver(Protocol):
    async def prepare(self, snapshot: dict, tracker: ExchangeTracker) -> None: ...
    async def call(self, destination: str) -> dict: ...
    async def close(self) -> None: ...


async def execute_call(
    client: httpx.AsyncClient | None,
    runtime_service_token: str,
    run_id: str,
    endpoint_id: str,
    driver: CallDriver,
    spool_path: Path,
    *,
    heartbeat_seconds: float = 20,
    secrets: tuple[str, ...] = (),
    after_close: Callable[[], Awaitable[None]] | None = None,
    local_post: Callable[[str, dict], Awaitable[dict]] | None = None,
    local_ingestor: BatchIngestor | None = None,
) -> str:
    if not 0 < heartbeat_seconds <= 20:
        raise ValueError("Heartbeat interval must be within 20 seconds")
    token = str(uuid4())
    headers = {"X-Voice-Runtime-Token": runtime_service_token}

    async def post(suffix: str, body: dict) -> dict:
        if local_post is not None:
            return await local_post(suffix, body)
        if client is None:
            raise ValueError("HTTP client or local control service is required")
        response = await client.post(
            f"/api/runs/{run_id}/{suffix}",
            json=body,
            headers=headers,
            timeout=15,
            follow_redirects=False,
        )
        if response.status_code != 200:
            raise RuntimeError("Runtime control request rejected; no automatic retry")
        return response.json()

    claim_body = {"token": token, "endpoint_id": endpoint_id, "lease_seconds": 60}
    claim = await post("claim", claim_body)
    if claim["status"] != "claimed":
        raise RuntimeError("Execution already started; refusing repeat dial")
    # Mark dispatch BEFORE external work. A lost response must never lead to redial.
    await post("progress", {"token": token, "status": "running"})
    outcome, final_state, error = "failed", None, None
    diagnostics: list[dict] = []
    released, incomplete = False, False
    call_task = heartbeat_task = delivery_task = None
    spool = None
    if local_ingestor is not None:
        ingestor = local_ingestor
    elif client is not None:
        ingestor = ApiEvidenceIngestor(client, run_id, runtime_service_token)
    else:
        raise ValueError("HTTP client or local evidence ingestor is required")

    async def heartbeat():
        while True:
            await asyncio.sleep(heartbeat_seconds)
            await post("claim", claim_body)

    async def work():
        limit = claim["resolved_config"]["call_limits"]["max_duration_secs"]
        async with asyncio.timeout(limit):
            await driver.prepare(claim["resolved_config"], tracker)
            return await driver.call(claim["destination"])

    try:
        heartbeat_task = asyncio.create_task(heartbeat())
        spool = DurableSpool(spool_path)
        redacted_secrets = (*secrets, runtime_service_token) if runtime_service_token else secrets
        tracker = ExchangeTracker(run_id, spool, secrets=redacted_secrets)
        delivery_task = asyncio.create_task(stream_evidence(spool, ingestor))
        call_task = asyncio.create_task(work())
        done, _ = await asyncio.wait(
            (call_task, heartbeat_task, delivery_task), return_when=asyncio.FIRST_COMPLETED
        )
        if heartbeat_task in done:
            await heartbeat_task
        if delivery_task in done:
            await delivery_task
        final_state = await call_task
        outcome = "completed"
    except Exception as exc:
        logger.error("Call task failed for run {}", run_id)
        error = "Call execution failed; inspect structured diagnostics"
        diagnostics.append(
            exception_diagnostic(exc, code="call_execution_failed", message="Call execution failed")
        )
    except asyncio.CancelledError:
        error = "Call execution cancelled"
        raise
    finally:
        if call_task and not call_task.done():
            call_task.cancel()
        if call_task:
            await asyncio.gather(call_task, return_exceptions=True)
        try:
            async with asyncio.timeout(15):
                await driver.close()
            released = True
        except Exception:
            error = "Transport cleanup uncertain; endpoint remains reserved"
            diagnostics.append(
                diagnostic_dict(
                    severity="error",
                    category="transport_cleanup",
                    source="transport",
                    code="transport_cleanup_uncertain",
                    message="Transport cleanup was not confirmed; endpoint remains reserved",
                    uncertain=True,
                )
            )
        if released and after_close is not None:
            try:
                await after_close()
            except Exception:
                incomplete = True
                outcome, error = "failed", "Call artifacts incomplete; inspect runtime files"
                diagnostics.append(
                    diagnostic_dict(
                        severity="error",
                        category="artifact_failure",
                        source="runtime",
                        code="artifact_registration_failed",
                        message="Call artifacts could not be finalized",
                    )
                )
        # Stop and await uploader before final drain: only one cursor owner at a time.
        if delivery_task:
            delivery_task.cancel()
            delivery_result = await asyncio.gather(delivery_task, return_exceptions=True)
            if isinstance(delivery_result[0], Exception):
                incomplete = True
                outcome, error = "failed", "Evidence delivery failed; durable spool requires review"
                diagnostics.append(
                    diagnostic_dict(
                        severity="error",
                        category="evidence_delivery",
                        source="evidence",
                        code="evidence_delivery_failed",
                        message="Evidence delivery failed; durable spool requires review",
                        retryable=True,
                    )
                )
        try:
            if spool is None:
                raise RuntimeError("Evidence spool was not created")
            async with asyncio.timeout(15):
                await spool.flush()
                if not incomplete:
                    while await spool.deliver_once(ingestor):
                        pass
        except Exception:
            incomplete = True
            outcome, error = "failed", "Evidence incomplete; durable spool requires replay"
            diagnostics.append(
                diagnostic_dict(
                    severity="error",
                    category="evidence_delivery",
                    source="evidence",
                    code="evidence_incomplete",
                    message="Evidence is incomplete and requires spool replay",
                    retryable=True,
                )
            )
        finally:
            try:
                if spool is not None:
                    await spool.close()
            except Exception:
                incomplete = True
                outcome, error = "failed", "Evidence storage failed; durable spool requires review"
                diagnostics.append(
                    diagnostic_dict(
                        severity="error",
                        category="evidence_storage",
                        source="evidence",
                        code="evidence_storage_failed",
                        message="Evidence spool storage failed; durable review is required",
                    )
                )
            finally:
                if heartbeat_task:
                    heartbeat_task.cancel()
                    await asyncio.gather(heartbeat_task, return_exceptions=True)
        if released:
            await post(
                "progress",
                {
                    "token": token,
                    "status": outcome,
                    "transport_released": True,
                    "error": error,
                    "final_state": {"runtime": final_state, "evidence_incomplete": incomplete},
                    "diagnostics": diagnostics,
                },
            )
    if not released:
        raise RuntimeError("Transport cleanup uncertain; manual reconciliation required")
    return outcome
