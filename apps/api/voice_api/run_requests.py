"""Persist browser execution requests; transport dispatch is a separate runtime step."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from voice_runtime.contracts import AgentConfig

from voice_api.auth import require_operator
from voice_api.db import get_session
from voice_api.models import AgentVersion, Contact, Run
from voice_api.models.common import new_id

router = APIRouter(prefix="/api/runs", tags=["runs"])
Session = Depends(get_session)
Operator = Depends(require_operator)


class BrowserRunRequest(BaseModel):
    channel: Literal["browser"] = "browser"
    agent_version_id: str
    contact_id: str | None = None


@router.post("", status_code=201)
async def request_browser_run(
    body: BrowserRunRequest, session: AsyncSession = Session, _: None = Operator
) -> dict:
    version = await session.get(AgentVersion, body.agent_version_id)
    if version is None or version.status != "published":
        raise HTTPException(422, "Run requires a published agent version")
    contact = await session.get(Contact, body.contact_id) if body.contact_id else None
    if body.contact_id and contact is None:
        raise HTTPException(422, "Contact not found")
    run = Run(
        id=new_id(),
        channel="browser",
        agent_version_id=version.id,
        contact_id=body.contact_id,
        status="queued",
        resolved_config=AgentConfig.model_validate(version.config).model_dump(mode="json"),
        contact_snapshot={}
        if contact is None
        else {
            "id": contact.id,
            "name": contact.name,
            "timezone": contact.timezone,
        },
    )
    session.add(run)
    await session.commit()
    return {"run_id": run.id, "call_id": None, "status": run.status}
