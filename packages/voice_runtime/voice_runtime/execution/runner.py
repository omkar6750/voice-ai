"""One claimed call: fence before effects, renew ownership, always release transport first."""

import asyncio
import hashlib
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Protocol
from uuid import uuid4

import httpx

from voice_runtime.diagnostics import diagnostic_dict, exception_diagnostic
from voice_runtime.execution.delivery import finalize_evidence, stream_evidence
from voice_runtime.execution.evidence_client import ApiEvidenceIngestor
from voice_runtime.execution.exchange import ExchangeTracker
from voice_runtime.execution.spool import BatchIngestor, DurableSpool
from voice_runtime.execution.termination import TerminationSummary
from voice_runtime.safe_logs import RuntimeEvent, error_category, opaque_id, operational_event


def apply_transport_outcome(
    final_state: dict | None, transport_evidence: dict, diagnostics: list[dict]
) -> tuple[dict, str | None]:
    """Attach call-release evidence and refine a missing transport outcome."""
    state = dict(final_state or {})
    termination_data = state.get("termination")
    if not isinstance(termination_data, dict):
        state["call_outcome"] = transport_evidence
        return state, None

    termination = dict(termination_data)
    termination["transport_evidence"] = transport_evidence
    reason = transport_evidence.get("reason")
    if termination.get("cause") in {"unknown", "disconnect_unknown"} and reason in {
        "busy",
        "no_answer",
        "call_rejected",
        "dial_failed",
        "network_failure",
        "modem_failure",
        "remote_hangup",
        "remote_hangup_likely",
    }:
        termination["cause"] = reason
        confidence = transport_evidence.get("confidence")
        for diagnostic in diagnostics:
            if (
                diagnostic.get("category") == "call_termination"
                and diagnostic.get("code") == "disconnect_unknown"
            ):
                diagnostic["code"] = reason
                diagnostic["uncertain"] = confidence not in {"confirmed", "high"}
        state["termination"] = termination
        return state, reason
    state["termination"] = termination
    return state, None


def runtime_token_for_run(secret: str, run_id: str) -> str:
    return f"{run_id}.{hashlib.sha256(f'{secret}:{run_id}'.encode()).hexdigest()}"


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
    run_runtime_token = runtime_token_for_run(runtime_service_token, run_id)
    headers = {"X-Voice-Runtime-Token": run_runtime_token}

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
        ingestor = ApiEvidenceIngestor(client, run_id, run_runtime_token)
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
        if call_task in done:
            # If call completion races evidence shutdown, preserve the call outcome;
            # finalization reports evidence completeness independently.
            final_state = await call_task
        else:
            if heartbeat_task in done:
                await heartbeat_task
            if delivery_task in done:
                await delivery_task
            final_state = await call_task
        outcome = "completed"
        if isinstance(final_state, dict) and "termination" in final_state:
            termination = TerminationSummary.model_validate(final_state["termination"])
            outcome = termination.execution_status
            if outcome != "completed":
                error = f"Call ended without flow completion: {termination.cause}"
                diagnostics.append(
                    diagnostic_dict(
                        severity="warning",
                        category="call_termination",
                        source="call",
                        code=termination.cause,
                        message="Call ended without flow completion",
                        uncertain=termination.cause in {"unknown", "disconnect_unknown"},
                    )
                )
    except Exception as exc:
        outcome = "failed"
        operational_event(
            RuntimeEvent.CALL_FAILED,
            level="ERROR",
            error_category=error_category(exc),
            run_id=opaque_id(run_id),
        )
        error = "Call execution failed; inspect structured diagnostics"
        diagnostics.append(
            {
                **exception_diagnostic(
                    exc, code="call_execution_failed", message="Call execution failed"
                ),
                "detail": error_category(exc),
            }
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
                cleanup = await driver.close()
                if isinstance(cleanup, dict) and not cleanup.get("release_confirmed", False):
                    raise RuntimeError("Transport release unconfirmed")
            released = True
            if isinstance(final_state, dict) and isinstance(final_state.get("termination"), dict):
                final_state = {
                    **final_state,
                    "termination": {**final_state["termination"], "cleanup_status": "confirmed"},
                }
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
                diagnostics.append(
                    diagnostic_dict(
                        severity="error",
                        category="artifact_failure",
                        source="runtime",
                        code="artifact_registration_failed",
                        message="Call artifacts could not be finalized",
                    )
                )
        transport_evidence = getattr(driver, "call_outcome", None)
        if isinstance(transport_evidence, dict):
            final_state, release_reason = apply_transport_outcome(
                final_state, transport_evidence, diagnostics
            )
            if release_reason:
                error = f"Call ended without flow completion: {release_reason}"
        if spool is None:
            incomplete = True
        else:
            finalization = await finalize_evidence(spool, ingestor, delivery_task)
            incomplete = incomplete or finalization.incomplete
            if finalization.diagnostic:
                diagnostics.append(finalization.diagnostic)
        if incomplete and outcome != "completed":
            error = error or "Evidence incomplete; durable spool requires replay"
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
