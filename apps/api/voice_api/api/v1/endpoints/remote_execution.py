"""Endpoint registration and fenced call execution; expired work is uncertain, never retried."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from voice_api.api.deps import get_session, require_platform_admin, require_runtime_service
from voice_api.core.hosting import require_local_modem
from voice_api.db.tenant_scope import bind_organization, platform_admin_read
from voice_api.models import Call, Callback, Run, RuntimeEndpoint
from voice_api.models.common import new_id
from voice_api.schemas.execution import (
    Claim,
    EndpointBody,
    EndpointConfig,
    EndpointProbeResponse,
    EndpointStatus,
    Progress,
    RuntimeEndpointResponse,
    RuntimeEndpointsResponse,
)

router = APIRouter(tags=["execution"])
ACTIVE = ("claimed", "running", "uncertain")
Session = Depends(get_session)


def _endpoint_status(endpoint: RuntimeEndpoint, now: datetime) -> EndpointStatus:
    values = dict(endpoint.status or {})
    values["checked_at"] = values.get("checked_at") or endpoint.last_seen_at
    is_fresh = (
        endpoint.last_seen_at is not None and (now - endpoint.last_seen_at).total_seconds() < 120
    )
    values["alive"] = bool(values.get("alive", False) and is_fresh)
    return EndpointStatus.model_validate(values)


@router.get(
    "/runtime-endpoints",
    response_model=RuntimeEndpointsResponse,
    dependencies=[Depends(require_platform_admin)],
)
async def list_endpoints(session: AsyncSession = Session) -> dict:
    require_local_modem()
    rows = (await session.scalars(select(RuntimeEndpoint).order_by(RuntimeEndpoint.name))).all()
    active_runs = (
        await session.execute(
            platform_admin_read(select(Run.endpoint_id, Run.id).where(Run.status.in_(ACTIVE)))
        )
    ).all()
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
                "status": _endpoint_status(row, now),
                "last_seen_at": row.last_seen_at.isoformat() if row.last_seen_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
            for row in rows
        ]
    }


@router.get(
    "/runtime-endpoints/{endpoint_id}",
    response_model=RuntimeEndpointResponse,
    dependencies=[Depends(require_platform_admin)],
)
async def get_endpoint(endpoint_id: str, session: AsyncSession = Session) -> dict:
    require_local_modem()
    endpoint = await session.get(RuntimeEndpoint, endpoint_id)
    if endpoint is None:
        raise HTTPException(404, "Runtime endpoint not found")
    active = await session.scalar(
        platform_admin_read(
            select(Run.id).where(Run.endpoint_id == endpoint.id, Run.status.in_(ACTIVE))
        )
    )
    now = datetime.now(UTC)
    return {
        "id": endpoint.id,
        "name": endpoint.name,
        "config": endpoint.config,
        "active_run_id": active,
        "status": _endpoint_status(endpoint, now),
        "last_seen_at": endpoint.last_seen_at.isoformat() if endpoint.last_seen_at else None,
        "updated_at": endpoint.updated_at.isoformat() if endpoint.updated_at else None,
    }


@router.post(
    "/runtime-endpoints/{endpoint_id}/status", dependencies=[Depends(require_runtime_service)]
)
async def update_endpoint_status(
    endpoint_id: str, body: EndpointStatus, session: AsyncSession = Session
) -> dict:
    require_local_modem()
    endpoint = await session.get(RuntimeEndpoint, endpoint_id, with_for_update=True)
    if endpoint is None:
        raise HTTPException(404, "Runtime endpoint not found")
    now = datetime.now(UTC)
    endpoint.status = body.model_copy(update={"checked_at": now}).model_dump(mode="json")
    endpoint.last_seen_at = now
    await session.commit()
    return {"id": endpoint.id, "status": endpoint.status}


@router.post(
    "/runtime-endpoints/{endpoint_id}/probe",
    response_model=EndpointProbeResponse,
    dependencies=[Depends(require_platform_admin)],
)
async def probe_endpoint(endpoint_id: str, session: AsyncSession = Session) -> dict:
    require_local_modem()
    endpoint = await session.scalar(
        select(RuntimeEndpoint).where(RuntimeEndpoint.id == endpoint_id).with_for_update()
    )
    if endpoint is None:
        raise HTTPException(404, "Runtime endpoint not found")

    active_run = await session.scalar(
        platform_admin_read(
            select(Run.id).where(Run.endpoint_id == endpoint.id, Run.status.in_(ACTIVE)).limit(1)
        )
    )
    if active_run:
        raise HTTPException(409, "A call owns this modem; connection probing is paused")

    config = EndpointConfig.model_validate(endpoint.config)
    from voice_api.services.runtime_dispatch import control

    response = await control("/v1/modems/probe", config.model_dump(mode="json"))
    status = EndpointStatus.model_validate(response["status"])

    endpoint.status = status.model_dump(mode="json")
    endpoint.last_seen_at = datetime.now(UTC)
    await session.commit()
    return {"id": endpoint.id, "status": status}


@router.post("/runtime-endpoints", status_code=201, dependencies=[Depends(require_platform_admin)])
async def register(body: EndpointBody, session: AsyncSession = Session) -> dict:
    require_local_modem()
    if body.config.at_port == body.config.audio_port:
        raise HTTPException(422, "AT and audio ports must differ")
    endpoint = RuntimeEndpoint(
        id=new_id(), name=body.name, config=body.config.model_dump(mode="json")
    )
    session.add(endpoint)
    await session.commit()
    return {"id": endpoint.id}


@router.post("/runs/{run_id}/claim", dependencies=[Depends(require_runtime_service)])
async def claim(run_id: str, body: Claim, session: AsyncSession = Session) -> dict:
    raise HTTPException(409, "Separate runtime owns call execution; legacy claim disabled")


@router.post("/runs/{run_id}/progress", dependencies=[Depends(require_runtime_service)])
async def progress(run_id: str, body: Progress, session: AsyncSession = Session) -> dict:
    raise HTTPException(409, "Separate runtime owns progress; use runtime synchronization")


@router.post(
    "/runtime-endpoints/{endpoint_id}/recover", dependencies=[Depends(require_platform_admin)]
)
async def recover(endpoint_id: str, session: AsyncSession = Session) -> dict:
    require_local_modem()
    endpoint = await session.get(RuntimeEndpoint, endpoint_id, with_for_update=True)
    if endpoint is None:
        raise HTTPException(404, "Runtime endpoint not found")
    run = await session.scalar(
        platform_admin_read(
            select(Run)
            .where(
                Run.endpoint_id == endpoint_id,
                Run.status.in_(("claimed", "running")),
                Run.lease_expires_at <= datetime.now(UTC),
            )
            .with_for_update()
        )
    )
    if run:
        bind_organization(session.sync_session, run.org_id)
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
