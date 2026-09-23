"""Explicit operator recovery after verifying a dead worker no longer owns transport."""

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from voice_runtime.contracts.base import ConfigModel

from voice_api.auth import require_operator
from voice_api.db import get_session
from voice_api.evidence_security import safe_evidence
from voice_api.models import Call, Callback, Run, RuntimeEndpoint

router = APIRouter(prefix="/api/runs", tags=["execution"], dependencies=[Depends(require_operator)])
Session = Depends(get_session)


class ReconcileBody(ConfigModel):
    transport_idle_verified: Literal[True]
    worker_stopped_verified: Literal[True]
    note: str = Field(min_length=1, max_length=1000)


@router.post("/{run_id}/reconcile")
async def reconcile(run_id: str, body: ReconcileBody, session: AsyncSession = Session) -> dict:
    endpoint_id = await session.scalar(select(Run.endpoint_id).where(Run.id == run_id))
    if endpoint_id is None:
        raise HTTPException(404, "Telephone run endpoint not found")
    await session.get(RuntimeEndpoint, endpoint_id, with_for_update=True)
    run = await session.get(Run, run_id, with_for_update=True, populate_existing=True)
    if run.status != "uncertain":
        raise HTTPException(409, "Only uncertain runs require reconciliation")
    run.status = "failed"
    run.final_state = {
        "evidence_incomplete": True,
        "reconciled_at": datetime.now(UTC).isoformat(),
        "transport_idle_verified": True,
        "worker_stopped_verified": True,
        "operator_note": safe_evidence(body.note),
    }
    # Do not invent actual hangup time or success for an uncertain external call.
    call = await session.scalar(select(Call).where(Call.run_id == run_id))
    if call:
        call.status = "failed"
        callback = await session.scalar(
            select(Callback).where(Callback.call_id == call.id).with_for_update()
        )
        if callback:
            callback.status = "failed"
    await session.commit()
    return {"status": run.status, "redialed": False}
