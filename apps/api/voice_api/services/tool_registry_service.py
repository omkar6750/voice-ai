"""Validate DB tool/agent references against the canonical runtime registry."""

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from voice_runtime.contracts import AgentConfig, ToolConfig, registered_handler_specs

from voice_api.models import (
    Agent,
    AgentVersion,
    AgentVersionTool,
    Tool,
    ToolInvocation,
    ToolVersion,
)
from voice_api.schemas.tools import ToolValidationIssue, ToolValidationReport


def _issue(
    severity: str,
    code: str,
    scope: str,
    message: str,
    record_id: str | None = None,
    **metadata,
) -> ToolValidationIssue:
    return ToolValidationIssue(
        severity=severity,
        code=code,
        scope=scope,
        record_id=record_id,
        message=message,
        metadata=metadata,
    )


async def validate_tool_registry(session: AsyncSession) -> ToolValidationReport:
    """Return a deterministic report without mutating authoring or evidence data."""

    issues: list[ToolValidationIssue] = []
    tools = (await session.scalars(select(Tool))).all()
    tool_by_id = {row.id: row for row in tools}
    tool_versions = (await session.scalars(select(ToolVersion))).all()
    tool_version_by_id = {row.id: row for row in tool_versions}
    agent_versions = (await session.scalars(select(AgentVersion))).all()
    bindings = (await session.scalars(select(AgentVersionTool))).all()
    bindings_by_agent = {}
    for row in bindings:
        bindings_by_agent.setdefault(row.agent_version_id, []).append(row)

    supported = {spec.name for spec in registered_handler_specs() if spec.runtime_supported}
    for version in tool_versions:
        owner = tool_by_id.get(version.tool_id)
        config = version.config or {}
        try:
            parsed = ToolConfig.model_validate(config)
        except Exception as exc:
            issues.append(
                _issue(
                    "error",
                    "invalid_tool_config",
                    "tool_version",
                    f"Tool version config is invalid: {exc}",
                    version.id,
                    version_number=version.version,
                )
            )
            continue
        if owner is None:
            issues.append(
                _issue(
                    "error",
                    "missing_tool_owner",
                    "tool_version",
                    "Tool version references a missing logical tool.",
                    version.id,
                )
            )
        elif parsed.name != owner.name:
            issues.append(
                _issue(
                    "error",
                    "tool_name_mismatch",
                    "tool_version",
                    f"Config name '{parsed.name}' does not match tool '{owner.name}'.",
                    version.id,
                )
            )
        if parsed.kind == "registered" and parsed.handler not in supported:
            issues.append(
                _issue(
                    "error",
                    "unsupported_registered_handler",
                    "tool_version",
                    f"Registered handler '{parsed.handler}' is not in the runtime registry.",
                    version.id,
                    handler=parsed.handler,
                )
            )

    for version in agent_versions:
        rows = bindings_by_agent.get(version.id, [])
        row_map = {row.binding_key: row for row in rows}
        try:
            config = AgentConfig.model_validate(version.config or {})
        except Exception as exc:
            issues.append(
                _issue(
                    "error",
                    "invalid_agent_config",
                    "agent_version",
                    f"Agent version config is invalid: {exc}",
                    version.id,
                    version_number=version.version,
                )
            )
            continue

        configured = config.tool_bindings
        if set(row_map) != set(configured):
            issues.append(
                _issue(
                    "error",
                    "binding_rows_mismatch",
                    "agent_version",
                    "Relational bindings do not match the agent config bindings.",
                    version.id,
                    config_keys=sorted(configured),
                    row_keys=sorted(row_map),
                )
            )
        for key, binding in configured.items():
            row = row_map.get(key)
            if row is None:
                continue
            tool_version = tool_version_by_id.get(binding.tool_version_id)
            if row.tool_version_id != binding.tool_version_id:
                issues.append(
                    _issue(
                        "error",
                        "binding_version_mismatch",
                        "agent_version_tool",
                        f"Binding '{key}' points to a different version in the relational row.",
                        version.id,
                        binding_key=key,
                    )
                )
            if tool_version is None:
                issues.append(
                    _issue(
                        "error",
                        "missing_tool_version",
                        "agent_version_tool",
                        f"Binding '{key}' references a missing tool version.",
                        version.id,
                        binding_key=key,
                        tool_version_id=binding.tool_version_id,
                    )
                )
                continue
            if tool_version.tool_id != binding.tool_id:
                issues.append(
                    _issue(
                        "error",
                        "binding_owner_mismatch",
                        "agent_version_tool",
                        f"Binding '{key}' tool owner does not match its pinned tool version.",
                        version.id,
                        binding_key=key,
                    )
                )
            if version.status == "published" and tool_version.status != "published":
                issues.append(
                    _issue(
                        "error",
                        "published_agent_uses_draft_tool",
                        "agent_version_tool",
                        f"Published agent binding '{key}' uses a non-published tool version.",
                        version.id,
                        binding_key=key,
                        tool_version_id=tool_version.id,
                    )
                )

    agents = (await session.scalars(select(Agent))).all()
    agent_versions_by_id = {row.id: row for row in agent_versions}
    for agent in agents:
        if not agent.active_version_id:
            issues.append(
                _issue(
                    "warning",
                    "agent_without_active_version",
                    "agent",
                    "Agent has no active version.",
                    agent.id,
                )
            )
            continue
        active = agent_versions_by_id.get(agent.active_version_id)
        if active is None or active.agent_id != agent.id or active.status != "published":
            issues.append(
                _issue(
                    "error",
                    "invalid_active_version",
                    "agent",
                    "Active version is missing, belongs to another agent, or is not published.",
                    agent.id,
                    active_version_id=agent.active_version_id,
                )
            )

    referenced_tool_versions = {row.tool_version_id for row in bindings}
    invoked_tool_versions = set(
        (await session.scalars(select(ToolInvocation.tool_version_id))).all()
    )
    cleanup_candidates = []
    for version in tool_versions:
        if (
            version.status == "draft"
            and version.id not in referenced_tool_versions
            and version.id not in invoked_tool_versions
        ):
            cleanup_candidates.append(version.id)
            issues.append(
                _issue(
                    "warning",
                    "unreferenced_draft_tool_version",
                    "tool_version",
                    "Draft tool version is not referenced by an agent or historical invocation.",
                    version.id,
                )
            )

    return ToolValidationReport(
        generated_at=datetime.now(UTC),
        valid=not any(issue.severity == "error" for issue in issues),
        handlers=registered_handler_specs(),
        issues=issues,
        cleanup_candidates=cleanup_candidates,
    )


async def cleanup_unreferenced_drafts(session: AsyncSession) -> list[str]:
    """Delete only draft tool versions with no binding or evidence reference."""

    bindings = set((await session.scalars(select(AgentVersionTool.tool_version_id))).all())
    invoked = set((await session.scalars(select(ToolInvocation.tool_version_id))).all())
    candidates = (
        await session.scalars(
            select(ToolVersion).where(ToolVersion.status == "draft")
        )
    ).all()
    removable = [row for row in candidates if row.id not in bindings and row.id not in invoked]
    if removable:
        await session.execute(delete(ToolVersion).where(ToolVersion.id.in_([r.id for r in removable])))
        await session.commit()
    return [row.id for row in removable]
