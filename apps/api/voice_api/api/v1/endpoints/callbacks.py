"""Confirmed callbacks enqueue exactly one pinned call under a database row lock."""

from datetime import UTC, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException
from pydantic import AwareDatetime, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from voice_api.api.deps import get_session, require_operator
from voice_api.models import AgentVersion, Callback, Contact, WorkspaceSettings
from voice_api.services.call_service import queue_call
from voice_runtime.contracts import WorkspaceConfig
from voice_runtime.contracts.base import ConfigModel

Session = Depends(get_session)

router = APIRouter(tags=["callbacks"], dependencies=[Depends(require_operator)])


class ScheduleCallback(ConfigModel):
    request_key: str = Field(min_length=1, max_length=120)
    contact_id: str
    agent_version_id: str
    due_at: AwareDatetime
    timezone: str
    original_phrase: str = Field(min_length=1)

    @field_validator("timezone")
    @classmethod
    def known_zone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Use a valid IANA contact timezone") from None
        return value


class LaunchCallback(ConfigModel):
    endpoint_id: str
    mode: Literal["manual", "automatic"] = "manual"


@router.post("/callbacks", status_code=201)
async def schedule(body: ScheduleCallback, session: AsyncSession = Session) -> dict:
    # Serialize creation per contact, including retries with the same request key.
    contact = await session.get(Contact, body.contact_id, with_for_update=True)
    version = await session.get(AgentVersion, body.agent_version_id)
    if contact is None or version is None or version.status != "published":
        raise HTTPException(422, "Callback requires contact and published agent")
    existing = await session.scalar(
        select(Callback).where(Callback.request_key == body.request_key)
    )
    if existing:
        if any(getattr(existing, key) != value for key, value in body.model_dump().items()):
            raise HTTPException(409, "Callback request key already used")
        return {"id": existing.id, "status": existing.status}
    callback = Callback(**body.model_dump())
    session.add(callback)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(409, "Callback request key already used") from None
    return {"id": callback.id, "status": callback.status}


@router.get("/callbacks")
async def list_callbacks(session: AsyncSession = Session) -> dict:
    rows = (await session.scalars(select(Callback).order_by(Callback.due_at.asc()))).all()
    return {
        "callbacks": [
            {
                "id": c.id,
                "request_key": c.request_key,
                "contact_id": c.contact_id,
                "agent_version_id": c.agent_version_id,
                "due_at": c.due_at,
                "timezone": c.timezone,
                "original_phrase": c.original_phrase,
                "status": c.status,
                "call_id": c.call_id,
                "automatic_attempts": c.automatic_attempts,
            }
            for c in rows
        ]
    }


@router.post("/callbacks/{callback_id}/launch")
async def launch(callback_id: str, body: LaunchCallback, session: AsyncSession = Session) -> dict:
    callback = await session.get(
        Callback, callback_id, with_for_update=True, populate_existing=True
    )
    if callback is None:
        raise HTTPException(404, "Callback not found")
    if callback.status != "scheduled" or callback.call_id is not None:
        raise HTTPException(409, "Callback already claimed; uncertain attempts never redial")
    now = datetime.now(UTC)
    if body.mode == "automatic":
        row = await session.get(WorkspaceSettings, 1, with_for_update=True)
        config = WorkspaceConfig.model_validate(row.config if row else {})
        if not config.automatic_callbacks_enabled:
            raise HTTPException(409, "Automatic callbacks disabled")
        if callback.automatic_attempts or not callback.due_at <= now <= callback.due_at + timedelta(
            minutes=config.callback_due_window_minutes
        ):
            raise HTTPException(409, "Outside automatic due window; manual launch required")
        callback.automatic_attempts = 1
    run, call = await queue_call(
        session, callback.contact_id, callback.agent_version_id, body.endpoint_id
    )
    callback.status, callback.call_id = "queued", call.id
    callback.claimed_at, callback.claim_token = now, call.correlation_id
    await session.commit()
    return {"id": callback.id, "run_id": run.id, "call_id": call.id, "status": callback.status}
