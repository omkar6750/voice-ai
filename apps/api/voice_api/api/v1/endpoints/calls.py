import asyncio

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from voice_api.api.deps import get_session, require_operator
from voice_api.db.session import SessionFactory
from voice_api.models import Call, Run, RunArtifact
from voice_api.models.common import new_id
from voice_api.schemas.call import StartCallBody
from voice_api.services.call_service import queue_call

router = APIRouter(tags=["calls"])
Session = Depends(get_session)
Operator = Depends(require_operator)

_background_call_tasks: set[asyncio.Task] = set()


async def _run_live_call_background(phone_number: str, run_id: str, call_id: str) -> None:
    from scripts.demo_call import run_call

    logger.info("Initiating live hardware call for {} to {}...", call_id, phone_number)

    # 1. Fetch dynamic max_duration limit from the DB Run resolved_config
    max_duration = 600
    try:
        async with SessionFactory() as session:
            run = await session.get(Run, run_id)
            if run and run.resolved_config:
                max_duration = run.resolved_config.get("call_limits", {}).get("max_duration_secs", 600)
    except Exception as exc:
        logger.warning("Could not read call limit from run {}: {}", run_id, exc)

    recording_dir = None
    try:
        recording_dir = await run_call(phone_number, max_duration_secs=max_duration)
        logger.info("Live hardware call {} completed successfully (directory: {})", call_id, recording_dir)
        status = "completed"
    except Exception as exc:
        logger.error("Live hardware call {} failed: {}", call_id, exc)
        status = "failed"

    # 2. Persist call outcome and register artifacts in DB
    try:
        async with SessionFactory() as session:
            call = await session.get(Call, call_id)
            run = await session.get(Run, run_id)
            if call:
                call.status = status
                if recording_dir:
                    call.recording_path = str(recording_dir)
            if run:
                run.status = status

            if recording_dir and recording_dir.is_dir():
                for item in recording_dir.iterdir():
                    if item.is_file():
                        kind = "audio" if item.suffix in (".wav", ".mp3", ".pcm") else "log"
                        session.add(
                            RunArtifact(
                                id=new_id(),
                                run_id=run_id,
                                kind=kind,
                                path=str(item.resolve()),
                                size_bytes=item.stat().st_size,
                                sample_rate=16000 if kind == "audio" else None,
                                channels=1 if kind == "audio" else None,
                            )
                        )
            await session.commit()
    except Exception as exc:
        logger.error("Failed to update call records in db: {}", exc)


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


@router.get("/calls")
async def list_calls(session: AsyncSession = Session, _: None = Operator) -> dict:
    rows = (await session.scalars(select(Call).order_by(Call.created_at.desc()))).all()
    return {
        "calls": [
            {
                "id": c.id,
                "run_id": c.run_id,
                "contact_id": c.contact_id,
                "agent_version_id": c.agent_version_id,
                "target_snapshot": c.target_snapshot,
                "status": c.status,
                "recording_path": c.recording_path,
                "answered_at": c.answered_at,
                "ended_at": c.ended_at,
                "created_at": c.created_at,
            }
            for c in rows
        ]
    }


@router.get("/calls/{call_id}")
async def get_call(call_id: str, session: AsyncSession = Session, _: None = Operator) -> dict:
    call = await session.get(Call, call_id)
    if call is None:
        raise HTTPException(404, "Call not found")
    return {
        "id": call.id,
        "run_id": call.run_id,
        "contact_id": call.contact_id,
        "agent_version_id": call.agent_version_id,
        "target_snapshot": call.target_snapshot,
        "status": call.status,
        "recording_path": call.recording_path,
        "answered_at": call.answered_at,
        "ended_at": call.ended_at,
        "created_at": call.created_at,
    }


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

