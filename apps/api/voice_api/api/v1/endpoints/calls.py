from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from voice_api.api.deps import get_session, require_operator
from voice_api.schemas.call import StartCallBody
from voice_api.services.call_service import queue_call

router = APIRouter(tags=["calls"])
Session = Depends(get_session)
Operator = Depends(require_operator)


@router.post("/calls", status_code=201)
async def start_call(
    body: StartCallBody, session: AsyncSession = Session, _: None = Operator
) -> dict:
    run, call = await queue_call(
        session, body.contact_id, body.agent_version_id, body.endpoint_id, body.logging_override
    )
    await session.commit()
    return {"run_id": run.id, "call_id": call.id, "status": "queued"}
