"""Endpoint registration and fenced call execution; expired work is uncertain, never retried."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from voice_api.api.deps import get_session, require_operator
from voice_api.core.security import safe_evidence
from voice_api.models import Call, Callback, Run, RuntimeEndpoint
from voice_api.models.common import new_id
from voice_api.schemas.execution import Claim, EndpointBody, EndpointConfig, Progress
from voice_api.services.resolution_service import fingerprint

router = APIRouter(tags=["execution"], dependencies=[Depends(require_operator)])
ACTIVE = ("claimed", "running", "uncertain")
Session = Depends(get_session)


@router.get("/runtime-endpoints")
async def list_endpoints(session: AsyncSession = Session) -> dict:
    rows = (await session.scalars(select(RuntimeEndpoint).order_by(RuntimeEndpoint.name))).all()
    active_runs = (await session.scalars(select(Run).where(Run.status.in_(ACTIVE)))).all()
    active_by_endpoint = {run.endpoint_id: run.id for run in active_runs if run.endpoint_id}
    now = datetime.now(UTC)

    return {
        "endpoints": [
            {
                "id": row.id,
                "name": row.name,
                "config": row.config,
                "created_at": row.created_at,
                "active_run_id": active_by_endpoint.get(row.id),
                "status": row.status
                if row.status
                else {
                    "checked_at": row.last_seen_at.isoformat() if row.last_seen_at else None,
                    "alive": bool(
                        row.last_seen_at and (now - row.last_seen_at).total_seconds() < 120
                    ),
                    "sim_ready": None,
                    "can_make_call": None,
                    "radio_access": "unknown",
                    "rssi": None,
                    "usb_audio_active": None,
                    "last_error": None,
                },
                "last_seen_at": row.last_seen_at.isoformat() if row.last_seen_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
            for row in rows
        ]
    }


@router.get("/runtime-endpoints/{endpoint_id}")
async def get_endpoint(endpoint_id: str, session: AsyncSession = Session) -> dict:
    endpoint = await session.get(RuntimeEndpoint, endpoint_id)
    if endpoint is None:
        raise HTTPException(404, "Runtime endpoint not found")
    active = await session.scalar(
        select(Run.id).where(Run.endpoint_id == endpoint.id, Run.status.in_(ACTIVE))
    )
    now = datetime.now(UTC)
    return {
        "id": endpoint.id,
        "name": endpoint.name,
        "config": endpoint.config,
        "active_run_id": active,
        "status": endpoint.status
        or {
            "checked_at": endpoint.last_seen_at.isoformat() if endpoint.last_seen_at else None,
            "alive": bool(
                endpoint.last_seen_at and (now - endpoint.last_seen_at).total_seconds() < 120
            ),
            "sim_ready": None,
            "can_make_call": None,
            "radio_access": "unknown",
            "rssi": None,
            "usb_audio_active": None,
            "last_error": None,
        },
        "last_seen_at": endpoint.last_seen_at.isoformat() if endpoint.last_seen_at else None,
        "updated_at": endpoint.updated_at.isoformat() if endpoint.updated_at else None,
    }


@router.post("/runtime-endpoints/{endpoint_id}/status")
async def update_endpoint_status(
    endpoint_id: str, body: dict, session: AsyncSession = Session
) -> dict:
    endpoint = await session.get(RuntimeEndpoint, endpoint_id, with_for_update=True)
    if endpoint is None:
        raise HTTPException(404, "Runtime endpoint not found")
    now = datetime.now(UTC)
    endpoint.status = {
        "checked_at": now.isoformat(),
        "alive": bool(body.get("alive", True)),
        "sim_ready": body.get("sim_ready"),
        "can_make_call": body.get("can_make_call"),
        "radio_access": body.get("radio_access", "unknown"),
        "rssi": body.get("rssi"),
        "usb_audio_active": body.get("usb_audio_active"),
        "last_error": body.get("last_error"),
    }
    endpoint.last_seen_at = now
    await session.commit()
    return {"id": endpoint.id, "status": endpoint.status}


@router.post("/runtime-endpoints", status_code=201)
async def register(body: EndpointBody, session: AsyncSession = Session) -> dict:
    if body.config.at_port == body.config.audio_port:
        raise HTTPException(422, "AT and audio ports must differ")
    endpoint = RuntimeEndpoint(
        id=new_id(), name=body.name, config=body.config.model_dump(mode="json")
    )
    session.add(endpoint)
    await session.commit()
    return {"id": endpoint.id}


@router.post("/runs/{run_id}/claim")
async def claim(run_id: str, body: Claim, session: AsyncSession = Session) -> dict:
    # All competing calls serialize on the endpoint before touching run state.
    endpoint = await session.get(RuntimeEndpoint, body.endpoint_id, with_for_update=True)
    if endpoint is None:
        raise HTTPException(404, "Runtime endpoint not found")
    run = await session.get(Run, run_id, with_for_update=True, populate_existing=True)
    if run is None or run.channel != "phone":
        raise HTTPException(422, "Select a telephone run")
    if run.endpoint_id not in (None, endpoint.id):
        raise HTTPException(409, "Run belongs to another endpoint")
    now = datetime.now(UTC)
    if run.status in ("claimed", "running") and run.claim_token == body.token:
        if run.lease_expires_at is None or run.lease_expires_at <= now:
            raise HTTPException(409, "Lease expired; reconcile instead of redialing")
        run.lease_expires_at = now + timedelta(seconds=body.lease_seconds)
    elif run.status == "queued":
        occupied = await session.scalar(
            select(Run.id).where(Run.endpoint_id == endpoint.id, Run.status.in_(ACTIVE))
        )
        if occupied:
            raise HTTPException(409, "Endpoint occupied or awaiting reconciliation")
        config = EndpointConfig.model_validate(endpoint.config)
        if run.resolved_config.get("audio", {}).get("sample_rate") not in config.sample_rates:
            raise HTTPException(422, "Agent PCM rate is unsupported by endpoint")
        if config.at_port == config.audio_port:
            raise HTTPException(422, "AT and audio ports must differ")
        run.endpoint_id, run.claim_token, run.status = endpoint.id, body.token, "claimed"
        run.claimed_at = now
        run.lease_expires_at = now + timedelta(seconds=body.lease_seconds)
        snapshot = dict(run.resolved_config)
        snapshot["_resolved"] = {
            **snapshot.get("_resolved", {}),
            "endpoint": config.model_dump(mode="json"),
            "contact": run.contact_snapshot,
        }
        run.resolved_config, run.config_hash = snapshot, fingerprint(snapshot)
    else:
        raise HTTPException(409, "Run is not claimable")
    call = await session.scalar(select(Call).where(Call.run_id == run.id))
    if call is None:
        raise HTTPException(422, "Telephone run lacks call identity")
    await session.commit()
    return {
        "run_id": run.id,
        "call_id": call.id,
        "correlation_id": call.correlation_id,
        "destination": call.target_snapshot,
        "status": run.status,
        "resolved_config": run.resolved_config,
        "config_hash": run.config_hash,
        "lease_expires_at": run.lease_expires_at,
    }


@router.post("/runs/{run_id}/progress")
async def progress(run_id: str, body: Progress, session: AsyncSession = Session) -> dict:
    run = await session.get(Run, run_id, with_for_update=True, populate_existing=True)
    if run is None:
        raise HTTPException(404, "Run not found")
    if run.claim_token != body.token:
        raise HTTPException(409, "Stale execution token")
    if run.status in ("completed", "failed"):
        if (
            run.status != body.status
            or run.final_state != safe_evidence(body.final_state)
            or run.error != safe_evidence(body.error)
        ):
            raise HTTPException(409, "Conflicting final outcome")
        return {"status": run.status}
    now = datetime.now(UTC)
    if (
        run.status not in ("claimed", "running")
        or run.lease_expires_at is None
        or run.lease_expires_at <= now
    ):
        raise HTTPException(409, "Expired/uncertain execution requires reconciliation")
    if body.status != "running" and not body.transport_released:
        raise HTTPException(422, "Confirm transport cleanup before releasing endpoint")
    run.status = body.status
    run.started_at = run.started_at or now
    call = await session.scalar(select(Call).where(Call.run_id == run.id))
    if call:
        call.status = body.status
        if body.status == "running":
            call.started_at = call.started_at or now
            call.answered_at = call.answered_at or now
    if body.status != "running":
        run.ended_at, run.final_state, run.error = (
            now,
            safe_evidence(body.final_state),
            safe_evidence(body.error),
        )
        if call:
            call.ended_at = now
            callback = await session.scalar(
                select(Callback).where(Callback.call_id == call.id).with_for_update()
            )
            if callback:
                callback.status, callback.completed_at = body.status, now
    await session.commit()
    return {"status": run.status}


@router.post("/runtime-endpoints/{endpoint_id}/recover")
async def recover(endpoint_id: str, session: AsyncSession = Session) -> dict:
    endpoint = await session.get(RuntimeEndpoint, endpoint_id, with_for_update=True)
    if endpoint is None:
        raise HTTPException(404, "Runtime endpoint not found")
    run = await session.scalar(
        select(Run)
        .where(
            Run.endpoint_id == endpoint_id,
            Run.status.in_(("claimed", "running")),
            Run.lease_expires_at <= datetime.now(UTC),
        )
        .with_for_update()
    )
    if run:
        run.status = "uncertain"
        run.error = "Worker lease expired; inspect modem before explicit reconciliation"
        call = await session.scalar(select(Call).where(Call.run_id == run.id))
        if call:
            call.status = "uncertain"
            callback = await session.scalar(
                select(Callback).where(Callback.call_id == call.id).with_for_update()
            )
            if callback:
                callback.status = "uncertain"
        await session.commit()
    return {"run_id": run.id if run else None, "status": "uncertain" if run else "unchanged"}
