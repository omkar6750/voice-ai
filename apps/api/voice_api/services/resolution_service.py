"""Resolve immutable authoring bindings into one sanitized execution snapshot."""

import hashlib
import json
import subprocess
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from voice_runtime.contracts import AgentConfig, ToolConfig, WorkspaceConfig

from voice_api.core.security import safe_evidence
from voice_api.models import (
    AgentVersion,
    AgentVersionTool,
    KnowledgeBase,
    ToolVersion,
    WorkspaceSettings,
)


def fingerprint(config: dict) -> str:
    return hashlib.sha256(
        json.dumps(
            config, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
    ).hexdigest()


def application_identity() -> dict:
    root = Path(__file__).resolve().parents[3]
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
            timeout=2,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain", "--untracked-files=no"],
                cwd=root,
                capture_output=True,
                text=True,
                check=True,
                timeout=2,
            ).stdout
        )
    except (OSError, subprocess.SubprocessError):
        revision, dirty = None, None
    dependencies = {}
    for name in ("pipecat-ai", "pipecat-ai-flows", "pydantic", "sqlalchemy"):
        try:
            dependencies[name] = package_version(name)
        except PackageNotFoundError:
            dependencies[name] = None
    return {"revision": revision, "dirty": dirty, "dependencies": dependencies}


async def resolve(
    session: AsyncSession, version: AgentVersion, logging_override: bool | None = None
) -> tuple[dict, str]:
    config = AgentConfig.model_validate(version.config)
    settings = await session.get(WorkspaceSettings, 1)
    workspace = WorkspaceConfig.model_validate(settings.config if settings else {})
    tools = {}
    bindings = (
        await session.scalars(
            select(AgentVersionTool).where(AgentVersionTool.agent_version_id == version.id)
        )
    ).all()
    if {b.binding_key: b.tool_version_id for b in bindings} != {
        key: binding.tool_version_id for key, binding in config.tool_bindings.items()
    }:
        raise HTTPException(422, "Published tool bindings are inconsistent")
    for binding in bindings:
        tool = await session.get(ToolVersion, binding.tool_version_id)
        if tool is None or tool.status != "published":
            raise HTTPException(422, "Published tool unavailable")
        tools[binding.binding_key] = {
            "version_id": tool.id,
            "definition": ToolConfig.model_validate(tool.config).model_dump(mode="json"),
            "binding": binding.config,
        }
    knowledge = []
    for kb_id in config.knowledge_base_ids:
        kb = await session.get(KnowledgeBase, kb_id)
        if kb is None:
            raise HTTPException(422, "Knowledge base unavailable")
        knowledge.append({"id": kb.id, "name": kb.name})
    if knowledge and not any("knowledge" in k or k == "query_knowledge_base" for k in tools):
        tools["query_knowledge_base"] = {
            "version_id": "auto_kb_tool",
            "definition": {
                "kind": "registered",
                "name": "query_knowledge_base",
                "handler": "query_knowledge_base",
                "description": "Search attached knowledge base using hybrid vector retrieval to answer customer inquiries.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query or customer question to retrieve information for",
                        }
                    },
                    "required": ["query"],
                },
                "wait": {
                    "mode": "acknowledge_then_wait",
                    "acknowledgement": "Let me check our knowledge base for that.",
                },
            },
            "binding": {},
        }
    logs = (
        workspace.pipeline_logs_enabled
        if config.pipeline_logs == "inherit"
        else config.pipeline_logs == "enabled"
    )
    snapshot = safe_evidence(
        {
            **config.model_dump(mode="json"),
            "_resolved": {
                "schema_version": 1,
                "agent_version_id": version.id,
                "tools": tools,
                "knowledge": knowledge,
                "application": application_identity(),
                "pipeline_logs_enabled": logs if logging_override is None else logging_override,
                "logging_override": logging_override,
                "recording_retention_days": workspace.recording_retention_days,
                "pipeline_log_retention_days": workspace.pipeline_log_retention_days,
            },
        }
    )
    return snapshot, fingerprint(snapshot)
