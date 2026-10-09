"""Synchronize draft bindings and clone versioned definitions (ADR-0006)."""

from copy import deepcopy

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from voice_runtime.contracts import AgentConfig

from voice_api.models import (
    Agent,
    AgentVersion,
    AgentVersionKnowledge,
    AgentVersionTool,
    KnowledgeBase,
    Tool,
    ToolVersion,
)
from voice_api.models.common import new_id


async def sync_bindings(
    session: AsyncSession, version: AgentVersion, *, cloning_legacy: bool = False
) -> None:
    # Cloning must preserve older published instructions so operators can repair the draft.
    # All binding checks still apply; saves and publication keep strict validation.
    config = AgentConfig.model_validate(
        version.config, context={"read_legacy_config": True} if cloning_legacy else None
    )
    from voice_api.core.config import get_settings

    if config.credential_refs or get_settings().env != "dev":
        from voice_api.services.provider_credentials import resolve_references

        await resolve_references(session, config.model_dump(mode="json"), strict=True)
    for binding in config.tool_bindings.values():
        tool = await session.get(ToolVersion, binding.tool_version_id)
        if tool is None or tool.tool_id != binding.tool_id or tool.status != "published":
            raise HTTPException(422, "Binding requires matching published tool version")
    if len(set(config.knowledge_base_ids)) != len(config.knowledge_base_ids):
        raise HTTPException(422, "Knowledge base bindings must be unique")
    for base_id in config.knowledge_base_ids:
        if await session.get(KnowledgeBase, base_id) is None:
            raise HTTPException(422, "Knowledge base not found")
    previous = {
        row.binding_key: row.config
        for row in (
            await session.scalars(
                select(AgentVersionTool).where(AgentVersionTool.agent_version_id == version.id)
            )
        ).all()
    }
    await session.execute(
        delete(AgentVersionTool).where(AgentVersionTool.agent_version_id == version.id)
    )
    await session.execute(
        delete(AgentVersionKnowledge).where(AgentVersionKnowledge.agent_version_id == version.id)
    )
    session.add_all(
        [
            AgentVersionTool(
                agent_version_id=version.id,
                binding_key=key,
                tool_version_id=value.tool_version_id,
                config=previous.get(key, {}),
            )
            for key, value in config.tool_bindings.items()
        ]
    )
    session.add_all(
        [
            AgentVersionKnowledge(agent_version_id=version.id, knowledge_base_id=base_id)
            for base_id in config.knowledge_base_ids
        ]
    )
    await session.flush()


async def clone_version(session: AsyncSession, source_id: str, kind: str, revision: int) -> dict:
    model, owner_model, owner_key = (
        (AgentVersion, Agent, "agent_id") if kind == "agent" else (ToolVersion, Tool, "tool_id")
    )
    source = await session.get(model, source_id)
    if source is None:
        raise HTTPException(404, "Version not found")
    owner_id = getattr(source, owner_key)
    # Parent lock serializes version number allocation across different source versions.
    await session.get(owner_model, owner_id, with_for_update=True)
    source = await session.get(model, source_id, with_for_update=True, populate_existing=True)
    if source.revision != revision:
        raise HTTPException(409, "Source changed; reload before cloning")
    latest = await session.scalar(
        select(func.max(model.version)).where(getattr(model, owner_key) == owner_id)
    )
    clone = model(
        id=new_id(),
        **{owner_key: owner_id},
        version=latest + 1,
        revision=1,
        status="draft",
        parent_id=source.id,
        config=deepcopy(source.config),
    )
    if kind == "agent" and clone.config.get("stt", {}).get("model") == "saaras:v3":
        # Upgrade only the new draft. The source snapshot remains immutable.
        clone.config["stt"]["model"] = "saaras:v3-realtime"
    session.add(clone)
    await session.flush()
    if kind == "agent":
        await sync_bindings(session, clone, cloning_legacy=True)
        source_bindings = (
            await session.scalars(
                select(AgentVersionTool).where(AgentVersionTool.agent_version_id == source.id)
            )
        ).all()
        for binding in source_bindings:
            copied = await session.get(AgentVersionTool, (clone.id, binding.binding_key))
            copied.config = deepcopy(binding.config)
    await session.commit()
    return {
        "id": clone.id,
        "version": clone.version,
        "revision": clone.revision,
        "status": clone.status,
    }
