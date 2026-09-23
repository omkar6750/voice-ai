import asyncio

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from voice_api.api.deps import get_session, require_operator
from voice_api.db.session import SessionFactory
from voice_api.models import Call, Run
from voice_api.schemas.call import StartCallBody
from voice_api.services.call_service import queue_call

router = APIRouter(tags=["calls"])
Session = Depends(get_session)
Operator = Depends(require_operator)

_background_call_tasks: set[asyncio.Task] = set()


async def _run_live_call_background(phone_number: str, run_id: str, call_id: str) -> None:
    from scripts.demo_call import run_call

    logger.info("Initiating live hardware call for {} to {}...", call_id, phone_number)
    try:
        await run_call(phone_number)
        logger.info("Live hardware call {} completed successfully", call_id)
        status = "completed"
    except Exception as exc:
        logger.error("Live hardware call {} failed: {}", call_id, exc)
        status = "failed"

    try:
        async with SessionFactory() as session:
            call = await session.get(Call, call_id)
            run = await session.get(Run, run_id)
            if call:
                call.status = status
            if run:
                run.status = status
            await session.commit()
    except Exception as exc:
        logger.error("Failed to update call status in db: {}", exc)


def _spawn_call_task(phone_number: str, run_id: str, call_id: str) -> None:
    task = asyncio.create_task(_run_live_call_background(phone_number, run_id, call_id))
    _background_call_tasks.add(task)
    task.add_done_callback(_background_call_tasks.discard)


@router.post("/calls", status_code=201)
async def start_call(
    body: StartCallBody, session: AsyncSession = Session, _: None = Operator
) -> dict:
    run, call = await queue_call(
        session, body.contact_id, body.agent_version_id, body.endpoint_id, body.logging_override
    )
    if body.dispatch:
        call.status = "running"
        run.status = "running"
    await session.commit()

    if body.dispatch:
        _spawn_call_task(call.target_snapshot, run.id, call.id)
        return {
            "run_id": run.id,
            "call_id": call.id,
            "status": "calling",
            "target": call.target_snapshot,
        }

    return {"run_id": run.id, "call_id": call.id, "status": "queued"}


@router.post("/calls/{call_id}/dispatch")
async def dispatch_queued_call(
    call_id: str, session: AsyncSession = Session, _: None = Operator
) -> dict:
    call = await session.get(Call, call_id)
    if call is None:
        raise HTTPException(404, "Call not found")
    if call.status not in ("queued", "failed"):
        raise HTTPException(400, f"Call is already {call.status}")

    run = await session.get(Run, call.run_id) if call.run_id else None
    call.status = "running"
    if run:
        run.status = "running"
    await session.commit()

    _spawn_call_task(call.target_snapshot, call.run_id or "", call.id)
    return {
        "run_id": call.run_id,
        "call_id": call.id,
        "status": "calling",
        "target": call.target_snapshot,
    }

