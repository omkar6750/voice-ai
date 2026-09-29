"""Read-only choices for operator call dispatch."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from voice_api.api.deps import get_session, require_legacy_owner
from voice_api.models import Agent, AgentVersion, Run, RuntimeEndpoint
from voice_api.schemas.execution import EndpointConfig

router = APIRouter(tags=["calls"], dependencies=[Depends(require_legacy_owner)])
Session = Depends(get_session)


@router.get("/dial-options")
async def dial_options(session: AsyncSession = Session) -> dict:
    """Advertise published versions and saved endpoints, never inferred modem health."""
    agents = {agent.id: agent.name for agent in (await session.scalars(select(Agent))).all()}
    versions = (
        await session.scalars(
            select(AgentVersion)
            .where(AgentVersion.status == "published")
            .order_by(AgentVersion.agent_id, AgentVersion.version.desc())
        )
    ).all()
    endpoints = (
        await session.scalars(select(RuntimeEndpoint).order_by(RuntimeEndpoint.name))
    ).all()
    active = (
        await session.scalars(
            select(Run).where(Run.status.in_(("claimed", "running", "uncertain")))
        )
    ).all()
    active_by_endpoint = {run.endpoint_id: run.id for run in active if run.endpoint_id}
    return {
        "agent_versions": [
            {
                "id": row.id,
                "agent_id": row.agent_id,
                "agent_name": agents.get(row.agent_id, "Archived agent"),
                "version": row.version,
            }
            for row in versions
        ],
        "endpoints": [
            {
                "id": row.id,
                "name": row.name,
                "provider": EndpointConfig.model_validate(row.config).provider,
                "sample_rates": EndpointConfig.model_validate(row.config).sample_rates,
                "active_run_id": active_by_endpoint.get(row.id),
                "last_status": row.status,
                "last_seen_at": row.last_seen_at,
            }
            for row in endpoints
        ],
    }
