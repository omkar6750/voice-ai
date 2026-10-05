"""Versioned code-owned starter catalog for newly provisioned organizations."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from voice_runtime.contracts import (
    AgentConfig,
    FlowConfig,
    FlowMessageConfig,
    FlowNodeConfig,
    ToolBinding,
    ToolConfig,
    registered_handler_specs,
)

from voice_api.db.tenant_scope import bind_organization
from voice_api.models import (
    Agent,
    AgentVersion,
    Organization,
    Tool,
    ToolVersion,
    WorkspaceSettings,
)
from voice_api.models.common import new_id, now
from voice_api.services.publication_service import sync_bindings

SEED_MANIFEST_VERSION = 1
_SYSTEM_HANDLERS = ("change_node", "end_call")


async def seed_organization(session: AsyncSession, organization_id: str) -> None:
    """Install the minimal safe runtime catalog once, isolated to one new org."""
    bind_organization(session.sync_session, organization_id)
    organization = await session.scalar(
        select(Organization).where(Organization.id == organization_id).with_for_update()
    )
    if organization is None:
        raise ValueError("Organization does not exist")
    if organization.seed_manifest_version >= SEED_MANIFEST_VERSION:
        return
    session.add(WorkspaceSettings(id=1, org_id=organization_id, revision=1, config={}))

    specifications = {
        item.name: item for item in registered_handler_specs() if item.name in _SYSTEM_HANDLERS
    }
    tools: dict[str, tuple[Tool, ToolVersion]] = {}
    created_at = now()
    for handler in _SYSTEM_HANDLERS:
        specification = specifications[handler]
        tool = Tool(id=new_id(), org_id=organization_id, name=handler)
        version = ToolVersion(
            id=new_id(),
            org_id=organization_id,
            tool_id=tool.id,
            version=1,
            revision=1,
            status="published",
            published_at=created_at,
            config=ToolConfig(
                name=handler,
                description=specification.description,
                kind="registered",
                handler=handler,
                parameters=specification.parameters,
            ).model_dump(mode="json"),
        )
        session.add_all([tool, version])
        tools[handler] = (tool, version)
    await session.flush()

    bindings = {
        name: ToolBinding(tool_id=tool.id, tool_version_id=version.id)
        for name, (tool, version) in tools.items()
    }
    config = AgentConfig(
        name="Starter Voice Agent",
        system_prompt=(
            "You are a friendly, helpful voice assistant. Speak naturally and concisely. "
            "Ask one question at a time, listen carefully, and end the call politely when done."
        ),
        flow=FlowConfig(
            initial_node="greeting",
            nodes=[
                FlowNodeConfig(
                    id="greeting",
                    task_messages=[
                        FlowMessageConfig(
                            role="user",
                            content="Greet the caller using the configured instructions, then wait for their response.",
                        )
                    ],
                    prompt=(
                        "Greet the caller and ask how you can help. When they are ready to "
                        "continue, use change_node to move to conversation."
                    ),
                    transitions=["conversation"],
                    tool_bindings=list(_SYSTEM_HANDLERS),
                ),
                FlowNodeConfig(
                    id="conversation",
                    prompt=(
                        "Help the caller with their request. Keep replies short and natural. "
                        "When the caller is ready to finish, say goodbye and use end_call."
                    ),
                    tool_bindings=["end_call"],
                    terminal=True,
                ),
            ],
        ),
        tool_bindings=bindings,
    )
    agent = Agent(id=new_id(), org_id=organization_id, name=config.name)
    version = AgentVersion(
        id=new_id(),
        org_id=organization_id,
        agent_id=agent.id,
        version=1,
        revision=1,
        status="published",
        published_at=created_at,
        config=config.model_dump(mode="json"),
    )
    session.add_all([agent, version])
    await session.flush()
    await sync_bindings(session, version)
    agent.active_version_id = version.id
    organization.seed_manifest_version = SEED_MANIFEST_VERSION
    await session.flush()
