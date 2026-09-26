from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from voice_api.api.deps import get_session, require_operator
from voice_api.models import Tool, ToolVersion
from voice_api.models.common import new_id
from voice_api.schemas.agent import CreateBody, ExpectedRevision, RevisionBody
from voice_api.services.publication_service import clone_version
from voice_runtime.contracts import ToolConfig

router = APIRouter(tags=["tools"])
Session = Depends(get_session)
Operator = Depends(require_operator)


@router.get("/tools")
async def tools(session: AsyncSession = Session, _: None = Operator) -> dict:
    rows = (await session.scalars(select(Tool).order_by(Tool.name))).all()
    return {"tools": [{"id": row.id, "name": row.name} for row in rows]}


@router.get("/tools/handlers")
async def tool_handlers(_: None = Operator) -> dict:
    return {
        "handlers": [
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
                "name": "send_followup",
                "description": "Send a customized follow-up WhatsApp message/template to the contact.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "caller_name": {
                            "type": "string",
                            "description": "Recipient name",
                        },
                        "message": {
                            "type": "string",
                            "description": "Follow-up message content",
                        },
                    },
                },
                "runtime_supported": True,
                "category": "messaging",
            },
            {
                "name": "check_whatsapp_window",
                "description": "Verify whether an active 24-hour customer service window exists for direct freeform messaging.",
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
                "name": "classify_jev",
                "description": "Execute TypeSafe AI Jev System One multi-choice classification against configured question criteria on the live call state.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
                "runtime_supported": True,
                "category": "classification",
            },
            {
                "name": "classify_llm",
                "description": "Execute fast LLM multi-choice categorization or custom prompt analysis on the live call state.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
                "runtime_supported": True,
                "category": "classification",
            },
            {
                "name": "classify_lead",
                "description": "Alias for classify_jev multi-choice lead classification.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
                "runtime_supported": True,
                "category": "classification",
            },
            {
                "name": "check_callback_availability",
                "description": "Find available human callback slots within a caller-requested timeframe and configured role.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "timeframe": {"type": "string"},
                        "role": {"type": "string"},
                        "duration_minutes": {"type": "integer"},
                    },
                    "required": ["timeframe", "role"],
                },
                "runtime_supported": True,
                "category": "cadence",
            },
            {
                "name": "book_callback",
                "description": "Book one slot returned by check_callback_availability on the selected employee calendar.",
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
                "description": "Schedule an automated or operator callback based on caller request or spoken phrases like 'call me back tomorrow'.",
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
                    },
                    "required": ["time"],
                },
                "runtime_supported": True,
                "category": "cadence",
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


@router.post("/tools", status_code=201)
async def create_tool(
    body: CreateBody, session: AsyncSession = Session, _: None = Operator
) -> dict:
    config = ToolConfig.model_validate(body.config).model_dump(mode="json")
    if config["name"] != body.name:
        raise HTTPException(422, "Tool name must match configuration name")
    tool = Tool(id=new_id(), name=body.name)
    version = ToolVersion(id=new_id(), tool_id=tool.id, version=1, config=config)
    session.add(tool)
    await session.flush()
    session.add(version)
    await session.commit()
    return {"tool_id": tool.id, "version_id": version.id}


@router.get("/tools/{tool_id}/versions")
async def tool_versions(tool_id: str, session: AsyncSession = Session, _: None = Operator) -> dict:
    rows = (
        await session.scalars(
            select(ToolVersion).where(ToolVersion.tool_id == tool_id).order_by(ToolVersion.version)
        )
    ).all()
    return {
        "versions": [
            {
                "id": row.id,
                "version": row.version,
                "revision": row.revision,
                "status": row.status,
                "config": row.config,
            }
            for row in rows
        ]
    }


@router.patch("/tool-versions/{version_id}")
async def update_tool_version(
    version_id: str, body: RevisionBody, session: AsyncSession = Session, _: None = Operator
) -> dict:
    row = await session.get(ToolVersion, version_id, with_for_update=True)
    if row is None:
        raise HTTPException(404, "Tool version not found")
    if row.status != "draft":
        raise HTTPException(409, "Published versions are immutable")
    if row.revision != body.revision:
        raise HTTPException(409, "Draft changed by another operator")
    row.config = ToolConfig.model_validate(body.config).model_dump(mode="json")
    row.revision += 1
    await session.commit()
    return {"id": row.id, "revision": row.revision, "config": row.config}


@router.post("/tool-versions/{version_id}/publish")
async def publish_tool(
    version_id: str, body: ExpectedRevision, session: AsyncSession = Session, _: None = Operator
) -> dict:
    row = await session.get(ToolVersion, version_id, with_for_update=True)
    if row is None:
        raise HTTPException(404, "Tool version not found")
    if row.status != "draft":
        raise HTTPException(409, "Version is already published")
    ToolConfig.model_validate(row.config)
    if row.revision != body.revision:
        raise HTTPException(409, "Draft changed; reload before publishing")
    row.status, row.published_at = "published", datetime.now(UTC)
    await session.commit()
    return {"id": row.id, "status": row.status}


@router.post("/tool-versions/{version_id}/clone", status_code=201)
async def clone_tool(
    version_id: str, body: ExpectedRevision, session: AsyncSession = Session, _: None = Operator
) -> dict:
    return await clone_version(session, version_id, "tool", body.revision)
