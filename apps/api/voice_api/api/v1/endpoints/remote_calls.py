"""Queue telephone requests and launch the fenced, evidence-producing runtime."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from voice_api.api.deps import get_session, require_legacy_owner
from voice_api.core.hosting import require_hosted_call_admission
from voice_api.core.runtime_config import get_runtime_settings as get_settings
from voice_api.core.security import allow_organization_member
from voice_api.models import Call, Run
from voice_api.schemas.call import StartCallBody
from voice_api.services.call_service import queue_call
from voice_api.services.runtime_dispatch import dispatch

router = APIRouter(tags=["calls"])
Session = Depends(get_session)
Operator = Depends(require_legacy_owner)


@router.post("/calls", status_code=201)
async def start_call(
    body: StartCallBody, session: AsyncSession = Session, _: None = Operator
) -> dict:
    is_twilio = body.telephony is not None and body.telephony.provider == "twilio"
    if body.dispatch:
        if is_twilio:
            from voice_api.services.remote_twilio_dispatch import validate_twilio_dispatch_settings

            validate_twilio_dispatch_settings(get_settings())
        else:
            endpoint = body.telephony.endpoint_id if body.telephony else body.endpoint_id
            if not endpoint:
                raise HTTPException(422, "Dispatch needs an endpoint")

    run, call = await queue_call(
        session,
        body.contact_id,
        body.agent_version_id,
        body.endpoint_id,
        body.logging_override,
        body.telephony,
    )
    await session.commit()

    if body.dispatch:
        if is_twilio:
            from voice_api.services.remote_twilio_dispatch import dispatch_twilio_call

            call, _ = await dispatch_twilio_call(session, call, run, get_settings())
        else:
            endpoint = body.telephony.endpoint_id if body.telephony else body.endpoint_id
            await dispatch(session, run)

    return {
        "run_id": run.id,
        "call_id": call.id,
        "provider": getattr(call, "provider", "sim7600"),
        "status": call.status if is_twilio else ("dispatching" if body.dispatch else "queued"),
        "target": call.target_snapshot,
    }


@router.get("/calls")
@allow_organization_member
async def list_calls(session: AsyncSession = Session, _: None = Operator) -> dict:
    rows = (await session.scalars(select(Call).order_by(Call.created_at.desc()))).all()
    return {"calls": [_call_response(call) for call in rows]}


def _call_response(call: Call) -> dict:
    return {
        "id": call.id,
        "run_id": call.run_id,
        "contact_id": call.contact_id,
        "agent_version_id": call.agent_version_id,
        "target_snapshot": call.target_snapshot,
        "provider": call.provider,
        "from_number": call.from_number,
        "telephony_connection_id": call.telephony_connection_id,
        "status": call.status,
        "recording_path": call.recording_path,
        "answered_at": call.answered_at,
        "ended_at": call.ended_at,
        "created_at": call.created_at,
    }


@router.get("/calls/{call_id}")
@allow_organization_member
async def get_call(call_id: str, session: AsyncSession = Session, _: None = Operator) -> dict:
    call = await session.get(Call, call_id)
    if call is None:
        raise HTTPException(404, "Call not found")
    return _call_response(call)


@router.post("/calls/{call_id}/dispatch")
async def dispatch_queued_call(
    call_id: str, session: AsyncSession = Session, _: None = Operator
) -> dict:
    call = await session.get(Call, call_id)
    if call is None:
        raise HTTPException(404, "Call not found")
    if call.status != "queued":
        raise HTTPException(409, "Only queued calls can be dispatched")
    require_hosted_call_admission(call.provider)
    run = await session.get(Run, call.run_id) if call.run_id else None
    if run is None:
        raise HTTPException(404, "Run not found")

    if call.provider == "twilio":
        from voice_api.services.remote_twilio_dispatch import dispatch_twilio_call

        call, run = await dispatch_twilio_call(session, call, run, get_settings())
        return {
            "run_id": run.id,
            "call_id": call.id,
            "provider": call.provider,
            "status": call.status,
            "target": call.target_snapshot,
        }

    if not run.endpoint_id:
        raise HTTPException(422, "Dispatch needs an endpoint")
    await dispatch(session, run)
    return {
        "run_id": run.id,
        "call_id": call.id,
        "provider": call.provider,
        "status": "dispatching",
        "target": call.target_snapshot,
    }
