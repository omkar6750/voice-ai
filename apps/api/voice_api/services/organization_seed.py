"""Install the versioned, code-owned demo when provisioning a new organization."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from voice_api.db.tenant_scope import bind_organization
from voice_api.models import Agent, AgentVersion, Organization, WorkspaceSettings
from voice_api.models.common import new_id
from voice_api.services.organization_demo import demo_agent_config, seed_demo_run

SEED_MANIFEST_VERSION = 2


async def seed_organization(session: AsyncSession, organization_id: str) -> None:
    """Seed under the org lock; retries never duplicate or restore deleted demos."""
    bind_organization(session.sync_session, organization_id)
    organization = await session.scalar(
        select(Organization).where(Organization.id == organization_id).with_for_update()
    )
    if organization is None:
        raise ValueError("Organization does not exist")
    # New organizations only: preserve existing v1 starter catalogs and operator edits.
    if organization.seed_manifest_version > 0:
        return
    if await session.get(WorkspaceSettings, (1, organization_id)) is None:
        session.add(WorkspaceSettings(id=1, org_id=organization_id, revision=1, config={}))
    config = demo_agent_config()
    agent = Agent(id=new_id(), org_id=organization_id, name=config.name)
    version = AgentVersion(
        id=new_id(),
        org_id=organization_id,
        agent_id=agent.id,
        version=1,
        revision=1,
        status="draft",
        note=(
            "Demo starter adapted from Project Assistant v13. The linked run is a "
            "redacted historical example. Add your own provider credentials, then publish "
            "and activate this draft before making calls."
        ),
        config=config.model_dump(mode="json"),
    )
    # Native transitions and end_conversation need no ToolVersion rows or external bindings.
    session.add(agent)
    await session.flush()
    session.add(version)
    await session.flush()
    await seed_demo_run(session, organization_id, version)
    organization.seed_manifest_version = SEED_MANIFEST_VERSION
    await session.flush()
