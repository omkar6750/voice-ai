"""Persist a telephone request and its immutable destination before any external action."""

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from voice_api.models import AgentVersion, Call, Contact, Run, RuntimeEndpoint
from voice_api.models.common import new_id
from voice_api.resolution import resolve


async def queue_call(
    session: AsyncSession,
    contact_id: str,
    agent_version_id: str,
    endpoint_id: str | None,
    logging_override: bool | None = None,
) -> tuple[Run, Call]:
    contact = await session.get(Contact, contact_id)
    version = await session.get(AgentVersion, agent_version_id)
    if contact is None or version is None or version.status != "published":
        raise HTTPException(422, "Call requires contact and published agent")
    if endpoint_id and await session.get(RuntimeEndpoint, endpoint_id) is None:
        raise HTTPException(422, "Runtime endpoint not found")
    config, digest = await resolve(session, version, logging_override)
    run = Run(
        id=new_id(),
        status="queued",
        agent_version_id=version.id,
        endpoint_id=endpoint_id,
        contact_id=contact.id,
        resolved_config=config,
        config_hash=digest,
        snapshot_schema_version=1,
        contact_snapshot={
            "id": contact.id,
            "name": contact.name,
            "timezone": contact.timezone,
            "phone_number": contact.phone_number,
            "business": contact.business,
            "language": contact.language,
        },
    )
    session.add(run)
    await session.flush()
    call = Call(
        id=new_id(),
        correlation_id=new_id(),
        run_id=run.id,
        contact_id=contact.id,
        agent_version_id=version.id,
        target_snapshot=contact.phone_number,
        status="queued",
    )
    session.add(call)
    await session.flush()
    return run, call
