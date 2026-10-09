import re
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from voice_api.api.deps import get_session, require_legacy_owner
from voice_api.core.development import require_development_cleanup
from voice_api.core.security import allow_organization_member
from voice_api.models import (
    Agent,
    AgentVersion,
    AgentVersionTool,
    IntegrationConnection,
    IntegrationMedia,
    Tool,
    ToolInvocation,
    ToolVersion,
)
from voice_api.models.common import new_id
from voice_api.schemas.agent import ExpectedRevision
from voice_api.schemas.tools import (
    ToolCatalogResponse,
    ToolCleanupRequest,
    ToolCreateBody,
    ToolCreateResponse,
    ToolHandlerCatalog,
    ToolImpactResponse,
    ToolListResponse,
    ToolRevisionBody,
    ToolSummaryResponse,
    ToolUsagePage,
    ToolValidationReport,
    ToolValidationResponse,
    ToolVersionMutationResponse,
    ToolVersionPage,
    ToolVersionResponse,
    ToolVersionsResponse,
)
from voice_api.services.publication_service import clone_version
from voice_api.services.tool_registry_service import (
    cleanup_unreferenced_drafts,
    validate_tool_registry,
)
from voice_runtime.contracts import ToolConfig
from voice_runtime.contracts.prompt_references import tool_references

router = APIRouter(tags=["tools"])
Session = Depends(get_session)
Operator = Depends(require_legacy_owner)


async def _whatsapp_media_issue(session: AsyncSession, config: ToolConfig) -> str | None:
    if config.whatsapp_connection_id is not None:
        direct_connection = await session.get(IntegrationConnection, config.whatsapp_connection_id)
        if (
            direct_connection is None
            or direct_connection.provider != "whatsapp"
            or not direct_connection.enabled
            or direct_connection.deleted_at is not None
        ):
            return "Direct WhatsApp tool requires an enabled pinned WhatsApp connection"
    whatsapp = config.whatsapp
    if whatsapp is None:
        return None
    connection = await session.get(IntegrationConnection, whatsapp.connection_id)
    if (
        connection is None
        or connection.provider != "whatsapp"
        or not connection.enabled
        or connection.deleted_at is not None
    ):
        return "WhatsApp tool requires an enabled WhatsApp integration connection"
    header = whatsapp.header
    if header is None:
        return None
    media = await session.scalar(
        select(IntegrationMedia)
        .where(
            IntegrationMedia.connection_id == whatsapp.connection_id,
            IntegrationMedia.provider_media_id == header.media_id,
            IntegrationMedia.status == "available",
        )
        .with_for_update()
    )
    if media is None:
        return "Configured Meta media ID is unavailable on the selected WhatsApp connection"
    expected_type = {"IMAGE": "image", "VIDEO": "video", "DOCUMENT": "document"}[header.format]
    if media.media_type != expected_type:
        return f"Configured Meta media type must be {expected_type} for this template header"
    return None


def _remove_deleted_tool_references(
    raw_config: dict,
    *,
    tool_id: str,
    tool_version_ids: set[str],
    tool_name: str,
) -> tuple[dict, bool]:
    """Remove deleted tool bindings and prompt directives from an agent config."""
    config = dict(raw_config)
    changed = False
    bindings = dict(config.get("tool_bindings", {}))
    removed_binding_keys = {tool_name} if tool_name in bindings else set()
    for key, binding in bindings.items():
        if isinstance(binding, dict) and (
            binding.get("tool_id") == tool_id or binding.get("tool_version_id") in tool_version_ids
        ):
            removed_binding_keys.add(key)
    for key in removed_binding_keys:
        bindings.pop(key, None)
        changed = True

    reference_names = removed_binding_keys | {tool_name}
    reference_pattern = re.compile(
        rf"(?<!\\)#(?:{'|'.join(re.escape(name) for name in sorted(reference_names))})"
        r"\b(?:\s*\([^)]*\))?"
    )

    def remove_prompt_sentences(value: object) -> object:
        nonlocal changed
        if not isinstance(value, str):
            return value
        sentences = re.split(r"(?<=[.!?])(?=\s|$)", value)
        retained = [
            sentence for sentence in sentences if not (tool_references(sentence) & reference_names)
        ]
        cleaned = "".join(retained)
        cleaned = reference_pattern.sub("", cleaned)
        cleaned = re.sub(r"[ \t]+(?=\n)|\n[ \t]+", "\n", cleaned)
        if cleaned != value:
            changed = True
        return cleaned

    config["tool_bindings"] = bindings
    config["system_prompt"] = remove_prompt_sentences(config.get("system_prompt", ""))
    flow = dict(config.get("flow", {}))
    nodes = []
    for raw_node in flow.get("nodes", []):
        node = dict(raw_node)
        for prompt_key in ("prompt", "role_prompt", "role_message"):
            if prompt_key in node:
                node[prompt_key] = remove_prompt_sentences(node[prompt_key])
        for action_key in ("tool_bindings", "entry_actions", "exit_actions"):
            values = node.get(action_key, [])
            filtered = [value for value in values if value not in reference_names]
            if filtered != values:
                node[action_key] = filtered
                changed = True
        for action_key in ("pre_actions", "post_actions"):
            actions = node.get(action_key, [])
            filtered_actions = [
                action
                for action in actions
                if not (
                    isinstance(action, dict)
                    and action.get("type") == "function"
                    and action.get("handler") in reference_names
                )
            ]
            if filtered_actions != actions:
                node[action_key] = filtered_actions
                changed = True
        nodes.append(node)
    if "nodes" in flow:
        flow["nodes"] = nodes
    config["flow"] = flow
    global_functions = flow.get("global_functions", [])
    filtered_global = [
        function
        for function in global_functions
        if (function.get("name") if isinstance(function, dict) else function) not in reference_names
    ]
    if filtered_global != global_functions:
        flow["global_functions"] = filtered_global
        config["flow"] = flow
        changed = True

    background_hooks = config.get("background_hooks", [])
    filtered_hooks = [hook for hook in background_hooks if hook not in reference_names]
    if filtered_hooks != background_hooks:
        config["background_hooks"] = filtered_hooks
        changed = True
    return config, changed


@router.get("/tools", response_model=ToolListResponse | ToolCatalogResponse)
@allow_organization_member
async def tools(
    session: AsyncSession = Session, _: None = Operator, view: Literal["full", "summary"] = "full"
):
    if view == "summary":
        rows = (
            (
                await session.execute(
                    select(
                        Tool.id,
                        Tool.name,
                        func.max(ToolVersion.version)
                        .filter(ToolVersion.status == "published")
                        .label("latest_published_version"),
                        func.count(ToolVersion.id)
                        .filter(ToolVersion.status == "draft")
                        .label("draft_count"),
                    )
                    .outerjoin(ToolVersion, ToolVersion.tool_id == Tool.id)
                    .group_by(Tool.id, Tool.name)
                    .order_by(Tool.name)
                )
            )
            .mappings()
            .all()
        )
        return ToolCatalogResponse(tools=[dict(row) for row in rows])
    rows = (await session.scalars(select(Tool).order_by(Tool.name))).all()
    return ToolListResponse(tools=[ToolSummaryResponse(id=row.id, name=row.name) for row in rows])


@router.get("/tools/handlers")
@allow_organization_member
async def tool_handlers(_: None = Operator) -> ToolHandlerCatalog:
    from voice_runtime.contracts.registry import registered_handler_specs

    return {
        "handlers": [
            next(
                spec.model_dump()
                for spec in registered_handler_specs()
                if spec.name == "save_referral"
            ),
            {
                "name": "change_node",
                "description": "Transfer conversation flow to another connected node in the agent flow graph.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "node": {
                            "type": "string",
                            "description": "Identifier key of the destination node",
                        }
                    },
                    "required": ["node"],
                },
                "runtime_supported": True,
                "category": "flow",
            },
            {
                "name": "end_call",
                "description": "Terminate and hang up the current phone call.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "reason": {
                            "type": "string",
                            "description": "Optional closing explanation or reason",
                        }
                    },
                },
                "runtime_supported": True,
                "category": "telephony",
            },
            {
                "name": "send_whatsapp_template",
                "description": "Send an approved WhatsApp template with dynamic body parameters to the contact.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "caller_name": {
                            "type": "string",
                            "description": "Recipient name for template personalization",
                        },
                        "message": {
                            "type": "string",
                            "description": "Dynamic summary or body text for the template",
                        },
                    },
                },
                "runtime_supported": True,
                "category": "messaging",
            },
            {
                "name": "check_whatsapp_window",
                "description": "Verify whether an active 24-hour customer service window exists based on inbound messages.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "to": {
                            "type": "string",
                            "description": "E.164 phone number of the contact",
                        }
                    },
                    "required": ["to"],
                },
                "runtime_supported": True,
                "category": "messaging",
            },
            {
                "name": "send_whatsapp_message",
                "description": "Send a direct freeform WhatsApp text within the active 24-hour customer service window.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "to": {
                            "type": "string",
                            "description": "E.164 phone number of the contact",
                        },
                        "text": {
                            "type": "string",
                            "description": "Message text to send",
                        },
                    },
                    "required": ["to", "text"],
                },
                "runtime_supported": True,
                "category": "messaging",
            },
            {
                "name": "classify_lead",
                "description": "Classify the live lead using the classifier backend configured for this agent.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
                "runtime_supported": True,
                "category": "classification",
            },
            {
                "name": "check_callback_availability",
                "description": "Find available human callback slots within a caller-requested timeframe and configured role. Offer returned display labels exactly as written because they are speech-ready local times; never read slot IDs or timezone identifiers aloud.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "timeframe": {"type": "string"},
                        "role": {"type": "string"},
                    },
                    "required": ["timeframe", "role"],
                },
                "runtime_supported": True,
                "category": "cadence",
            },
            {
                "name": "book_callback",
                "description": "Book the caller-selected slot using the complete, unchanged slot_id returned by check_callback_availability. Wait for a successful result before confirming.",
                "parameters": {
                    "type": "object",
                    "properties": {"slot_id": {"type": "string"}, "reason": {"type": "string"}},
                    "required": ["slot_id", "reason"],
                },
                "runtime_supported": True,
                "category": "cadence",
            },
            {
                "name": "schedule_callback",
                "description": "Record a callback request for the contact's local date and time. An operator can launch it from the callback queue; this tool does not place a future call.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "time": {
                            "type": "string",
                            "description": "Requested callback date and time mentioned by caller (e.g. 'tomorrow at 10 AM', 'Monday 2 PM', 'in 2 hours')",
                        },
                        "reason": {
                            "type": "string",
                            "description": "Brief context or topic for the callback",
                        },
                        "timezone": {
                            "type": "string",
                            "description": "IANA timezone, required only when the contact timezone is unknown",
                        },
                    },
                    "required": ["time"],
                },
                "runtime_supported": True,
                "category": "cadence",
            },
            {
                "name": "query_knowledge_base",
                "description": "Search the agent's attached knowledge base(s) using hybrid RAG vector search to retrieve accurate information about company offerings, technical specifications, and pricing.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Natural language search query or customer question to retrieve relevant knowledge excerpts for",
                        },
                    },
                    "required": ["query"],
                },
                "runtime_supported": True,
                "category": "knowledge",
            },
        ],
        "http_policy": {
            "allowed_methods": ["GET", "POST", "PUT", "PATCH", "DELETE"],
            "allowed_schemes": ["https"],
            "credentials_policy": "URL credentials (user:pass) are forbidden; use a secret reference",
            "retry_policy": {
                "max_attempts": 5,
                "backoff_secs_min": 0,
                "write_idempotency_required": True,
            },
            "timeout_secs": {
                "min": 1,
                "max": 120,
                "default": 10,
            },
            "follow_redirects": False,
        },
    }


@router.get("/tools/validation", response_model=ToolValidationReport)
@allow_organization_member
async def validate_tools(
    session: AsyncSession = Session, _: None = Operator
) -> ToolValidationReport:
    """Validate all persisted tool and agent references without changing them."""

    return await validate_tool_registry(session)


@router.post("/tools/validation/cleanup", response_model=ToolValidationReport)
async def cleanup_tools(
    body: ToolCleanupRequest,
    session: AsyncSession = Session,
    _: None = Operator,
) -> ToolValidationReport:
    """Optionally remove only unreferenced draft tool versions, then revalidate."""

    cleaned = await cleanup_unreferenced_drafts(session) if body.apply else []
    report = await validate_tool_registry(session)
    report.cleaned_record_ids = cleaned
    return report


@router.post("/tools", status_code=201, response_model=ToolCreateResponse)
async def create_tool(
    body: ToolCreateBody, session: AsyncSession = Session, _: None = Operator
) -> ToolCreateResponse:
    config = body.config.model_dump(mode="json")
    if config["name"] != body.name:
        raise HTTPException(422, "Tool name must match configuration name")
    media_issue = await _whatsapp_media_issue(session, body.config)
    if media_issue:
        raise HTTPException(422, media_issue)
    tool = Tool(id=new_id(), name=body.name)
    version = ToolVersion(id=new_id(), tool_id=tool.id, version=1, config=config)
    session.add(tool)
    await session.flush()
    session.add(version)
    await session.commit()
    return ToolCreateResponse(tool_id=tool.id, version_id=version.id)


@router.get("/tools/{tool_id}/versions", response_model=ToolVersionsResponse | ToolVersionPage)
@allow_organization_member
async def tool_versions(
    tool_id: str,
    session: AsyncSession = Session,
    _: None = Operator,
    view: Literal["full", "summary"] = "full",
    status: Literal["draft", "published"] | None = None,
    before_version: int | None = Query(default=None, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
):
    if view == "summary":
        tool = await session.get(Tool, tool_id)
        if tool is None:
            raise HTTPException(404, "Tool not found")
        parent = aliased(ToolVersion)
        query = (
            select(
                ToolVersion.id,
                ToolVersion.tool_id,
                ToolVersion.version,
                ToolVersion.revision,
                ToolVersion.status,
                ToolVersion.created_at,
                ToolVersion.published_at,
                ToolVersion.parent_id,
                parent.version.label("parent_version"),
            )
            .outerjoin(
                parent,
                (parent.id == ToolVersion.parent_id) & (parent.tool_id == ToolVersion.tool_id),
            )
            .where(ToolVersion.tool_id == tool_id)
        )
        if status:
            query = query.where(ToolVersion.status == status)
        if before_version:
            query = query.where(ToolVersion.version < before_version)
        rows = (
            (await session.execute(query.order_by(ToolVersion.version.desc()).limit(limit + 1)))
            .mappings()
            .all()
        )
        more = len(rows) > limit
        page = rows[:limit]
        return ToolVersionPage(
            tool_id=tool.id,
            tool_name=tool.name,
            versions=[dict(row) for row in page],
            has_more=more,
            next_before_version=page[-1]["version"] if more else None,
        )
    rows = (
        await session.scalars(
            select(ToolVersion).where(ToolVersion.tool_id == tool_id).order_by(ToolVersion.version)
        )
    ).all()
    versions: list[ToolVersionResponse] = []
    for row in rows:
        versions.append(
            ToolVersionResponse(
                id=row.id,
                version=row.version,
                revision=row.revision,
                status=row.status,
                config=ToolConfig.model_validate(row.config or {}),
            )
        )
    return ToolVersionsResponse(versions=versions)


@router.get("/tool-versions/{version_id}", response_model=ToolVersionResponse)
@allow_organization_member
async def get_tool_version(
    version_id: str, tool_id: str, session: AsyncSession = Session, _: None = Operator
):
    row = await session.get(ToolVersion, version_id)
    if row is None or row.tool_id != tool_id:
        raise HTTPException(404, "Tool version not found")
    return ToolVersionResponse(
        id=row.id,
        version=row.version,
        revision=row.revision,
        status=row.status,
        config=ToolConfig.model_validate(row.config),
    )


@router.get("/tools/{tool_id}/usage", response_model=ToolUsagePage)
@allow_organization_member
async def tool_usage(
    tool_id: str,
    session: AsyncSession = Session,
    _: None = Operator,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
):
    if await session.get(Tool, tool_id) is None:
        raise HTTPException(404, "Tool not found")
    rows = (
        (
            await session.execute(
                select(
                    Agent.id.label("agent_id"),
                    Agent.name.label("agent_name"),
                    AgentVersion.id.label("agent_version_id"),
                    AgentVersion.version.label("agent_version"),
                    AgentVersion.status.label("agent_status"),
                    AgentVersionTool.binding_key,
                    ToolVersion.tool_id,
                    ToolVersion.id.label("tool_version_id"),
                    ToolVersion.version.label("tool_version"),
                )
                .select_from(AgentVersionTool)
                .join(ToolVersion, ToolVersion.id == AgentVersionTool.tool_version_id)
                .join(AgentVersion, AgentVersion.id == AgentVersionTool.agent_version_id)
                .join(Agent, Agent.id == AgentVersion.agent_id)
                .where(ToolVersion.tool_id == tool_id)
                .order_by(
                    Agent.name, Agent.id, AgentVersion.version.desc(), AgentVersionTool.binding_key
                )
                .offset(offset)
                .limit(limit + 1)
            )
        )
        .mappings()
        .all()
    )
    return ToolUsagePage(bindings=[dict(row) for row in rows[:limit]], has_more=len(rows) > limit)


@router.patch("/tool-versions/{version_id}")
async def update_tool_version(
    version_id: str,
    body: ToolRevisionBody,
    session: AsyncSession = Session,
    _: None = Operator,
) -> ToolVersionMutationResponse:
    row = await session.get(ToolVersion, version_id, with_for_update=True)
    if row is None:
        raise HTTPException(404, "Tool version not found")
    if row.status != "draft":
        raise HTTPException(409, "Published versions are immutable")
    if row.revision != body.revision:
        raise HTTPException(409, "Draft changed by another operator")
    media_issue = await _whatsapp_media_issue(session, body.config)
    if media_issue:
        raise HTTPException(422, media_issue)
    row.config = body.config.model_dump(mode="json")
    row.revision += 1
    await session.commit()
    return ToolVersionMutationResponse(
        id=row.id,
        revision=row.revision,
        status=row.status,
        config=body.config,
    )


@router.post("/tool-versions/{version_id}/validate", response_model=ToolValidationResponse)
async def validate_tool_version(
    version_id: str, session: AsyncSession = Session, _: None = Operator
) -> ToolValidationResponse:
    row = await session.get(ToolVersion, version_id)
    if row is None:
        raise HTTPException(404, "Tool version not found")
    try:
        config = ToolConfig.model_validate(row.config)
    except Exception as error:
        return ToolValidationResponse(
            id=row.id,
            valid=False,
            revision=row.revision,
            config=None,
            issues=[
                {
                    "severity": "error",
                    "code": "invalid_tool_config",
                    "scope": "tool_version",
                    "record_id": row.id,
                    "message": str(error),
                }
            ],
        )
    media_issue = await _whatsapp_media_issue(session, config)
    if media_issue:
        return ToolValidationResponse(
            id=row.id,
            valid=False,
            revision=row.revision,
            config=config,
            issues=[
                {
                    "severity": "error",
                    "code": "invalid_whatsapp_media_reference",
                    "scope": "tool_version",
                    "record_id": row.id,
                    "message": media_issue,
                }
            ],
        )
    return ToolValidationResponse(
        id=row.id,
        valid=True,
        revision=row.revision,
        config=config,
        issues=[],
    )


@router.post("/tool-versions/{version_id}/publish")
async def publish_tool(
    version_id: str, body: ExpectedRevision, session: AsyncSession = Session, _: None = Operator
) -> ToolVersionMutationResponse:
    row = await session.get(ToolVersion, version_id, with_for_update=True)
    if row is None:
        raise HTTPException(404, "Tool version not found")
    if row.status != "draft":
        raise HTTPException(409, "Version is already published")
    if row.revision != body.revision:
        raise HTTPException(409, "Draft changed; reload before publishing")
    config = ToolConfig.model_validate(row.config)
    media_issue = await _whatsapp_media_issue(session, config)
    if media_issue:
        raise HTTPException(422, media_issue)
    row.status, row.published_at = "published", datetime.now(UTC)
    await session.commit()
    return ToolVersionMutationResponse(id=row.id, status=row.status, revision=row.revision)


@router.post("/tool-versions/{version_id}/clone", status_code=201)
async def clone_tool(
    version_id: str, body: ExpectedRevision, session: AsyncSession = Session, _: None = Operator
) -> ToolVersionMutationResponse:
    return ToolVersionMutationResponse(
        **await clone_version(session, version_id, "tool", body.revision)
    )


@router.get("/tools/{tool_id}/impact", response_model=ToolImpactResponse)
@allow_organization_member
async def tool_deletion_impact(
    tool_id: str, session: AsyncSession = Session, _: None = Operator
) -> ToolImpactResponse:
    tool = await session.get(Tool, tool_id)
    if tool is None:
        raise HTTPException(404, "Tool not found")

    is_system_tool = tool.name in {"change_node", "end_call"}

    tv_ids = (
        await session.scalars(select(ToolVersion.id).where(ToolVersion.tool_id == tool_id))
    ).all()

    bindings = (
        (
            await session.scalars(
                select(AgentVersionTool).where(AgentVersionTool.tool_version_id.in_(tv_ids))
            )
        ).all()
        if tv_ids
        else []
    )

    referenced_version_ids = {binding.agent_version_id for binding in bindings}
    agent_versions = (await session.scalars(select(AgentVersion))).all()
    bound_agents = []
    for agent_version in agent_versions:
        _, has_config_reference = _remove_deleted_tool_references(
            agent_version.config or {},
            tool_id=tool_id,
            tool_version_ids=set(tv_ids),
            tool_name=tool.name,
        )
        if agent_version.id not in referenced_version_ids and not has_config_reference:
            continue
        agent = await session.get(Agent, agent_version.agent_id)
        bound_agents.append(
            {
                "agent_id": agent_version.agent_id,
                "agent_name": agent.name if agent else "Unknown Agent",
                "version": agent_version.version,
                "status": agent_version.status,
            }
        )

    return ToolImpactResponse(
        tool_id=tool.id,
        tool_name=tool.name,
        is_system_tool=is_system_tool,
        can_delete=not is_system_tool,
        system_tool_reason=(
            f"Tool '{tool.name}' is a core system-level tool critical for call transitions or hangup. It cannot be deleted."
            if is_system_tool
            else None
        ),
        bound_agents=bound_agents,
        versions_count=len(tv_ids),
    )


@router.delete("/tools/{tool_id}")
async def delete_tool(tool_id: str, session: AsyncSession = Session, _: None = Operator) -> dict:
    require_development_cleanup()
    tool = await session.get(Tool, tool_id)
    if tool is None:
        raise HTTPException(404, "Tool not found")
    if tool.name in {"change_node", "end_call"}:
        raise HTTPException(403, f"Tool '{tool.name}' is a core system tool and cannot be deleted")

    await session.execute(text("SET LOCAL session_replication_role = 'replica';"))

    tv_ids = (
        await session.scalars(select(ToolVersion.id).where(ToolVersion.tool_id == tool_id))
    ).all()

    tool_version_ids = set(tv_ids)
    if tool_version_ids:
        await session.execute(
            delete(AgentVersionTool).where(AgentVersionTool.tool_version_id.in_(tool_version_ids))
        )

    agent_versions = (await session.scalars(select(AgentVersion))).all()
    for av in agent_versions:
        cfg, changed = _remove_deleted_tool_references(
            av.config or {},
            tool_id=tool_id,
            tool_version_ids=tool_version_ids,
            tool_name=tool.name,
        )
        if changed:
            av.config = cfg
            av.revision += 1

    if tool_version_ids:
        # Keep historical invocation/result rows readable while the definition
        # is deleted; tool_version_id is nullable specifically for this case.
        await session.execute(
            update(ToolInvocation)
            .where(ToolInvocation.tool_version_id.in_(tool_version_ids))
            .values(tool_version_id=None)
        )

        await session.execute(delete(ToolVersion).where(ToolVersion.tool_id == tool_id))

    await session.execute(delete(Tool).where(Tool.id == tool_id))
    await session.commit()
    return {"status": "ok", "deleted_tool_id": tool_id, "tool_name": tool.name}
