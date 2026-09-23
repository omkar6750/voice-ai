"""One claimed call: fence before effects, renew ownership, always release transport first."""

import asyncio
from pathlib import Path
from typing import Protocol
from uuid import uuid4

import httpx

from voice_runtime.execution.evidence_client import ApiEvidenceIngestor
from voice_runtime.execution.exchange import ExchangeTracker
from voice_runtime.execution.spool import DurableSpool


class CallDriver(Protocol):
    async def prepare(self, snapshot: dict, tracker: ExchangeTracker) -> None: ...
    async def call(self, destination: str) -> dict: ...
    async def close(self) -> None: ...


async def execute_call(
    client: httpx.AsyncClient,
    operator_token: str,
    run_id: str,
    endpoint_id: str,
    driver: CallDriver,
    spool_path: Path,
    *,
    heartbeat_seconds: float = 20,
    secrets: tuple[str, ...] = (),
) -> str:
    if not 0 < heartbeat_seconds <= 20:
        raise ValueError("Heartbeat interval must be within 20 seconds")
    token = str(uuid4())
    headers = {"Authorization": f"Bearer {operator_token}"}

    async def post(suffix: str, body: dict) -> dict:
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
    spool = DurableSpool(spool_path)
    tracker = ExchangeTracker(run_id, spool, secrets=(*secrets, operator_token))
    outcome, final_state, error = "failed", None, None
    released, incomplete = False, False
    call_task = heartbeat_task = None

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
        call_task = asyncio.create_task(work())
        done, _ = await asyncio.wait(
            (call_task, heartbeat_task), return_when=asyncio.FIRST_COMPLETED
        )
        if heartbeat_task in done:
            await heartbeat_task
        final_state = await call_task
        outcome = "completed"
    except Exception:
        error = "Call execution failed; inspect sanitized evidence"
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
        try:
            async with asyncio.timeout(15):
                await spool.flush()
                ingestor = ApiEvidenceIngestor(client, run_id, operator_token)
                while await spool.deliver_once(ingestor):
                    pass
        except Exception:
            incomplete = True
            outcome, error = "failed", "Evidence incomplete; durable spool requires replay"
        finally:
            try:
                await spool.close()
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
                },
            )
    if not released:
        raise RuntimeError("Transport cleanup uncertain; manual reconciliation required")
    return outcome
