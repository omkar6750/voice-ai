"""Control plane. The runtime owns audio; this API owns durable state."""

from datetime import UTC, datetime
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from voice_runtime.contracts import AgentConfig, ToolConfig, WorkspaceConfig

from voice_api.auth import require_operator
from voice_api.db import get_session
from voice_api.evidence_ingestion import router as ingestion_router
from voice_api.evidence_read import related_evidence
from voice_api.evidence_routes import router as evidence_router
from voice_api.integrations.routes import router as integrations_router
from voice_api.knowledge.routes import router as knowledge_router
from voice_api.models import (
    Agent,
    AgentVersion,
    AgentVersionTool,
    Call,
    Contact,
    ConversationMessage,
    Exchange,
    Run,
    Tool,
    ToolInvocation,
    ToolVersion,
    TraceSpan,
    WorkspaceSettings,
)
from voice_api.models.common import new_id
from voice_api.publication import ExpectedRevision, sync_bindings
from voice_api.publication import router as publication_router
from voice_api.run_requests import router as run_requests_router

app = FastAPI(title="Voice AI API", version="0.2.0")
app.include_router(integrations_router)
app.include_router(knowledge_router)
app.include_router(publication_router)
app.include_router(run_requests_router)
app.include_router(evidence_router)
app.include_router(ingestion_router)
Session = Depends(get_session)
Operator = Depends(require_operator)


@app.exception_handler(RequestValidationError)
@app.exception_handler(ValidationError)
async def validation_error(_request, error):
    # Validation responses must not echo write-only credential inputs.
    return JSONResponse(
        status_code=422,
        content={
            "detail": [
                {"loc": list(item["loc"]), "type": item["type"], "msg": item["msg"]}
                for item in error.errors()
            ]
        },
    )


class RevisionBody(BaseModel):
    revision: int = Field(gt=0)
    config: dict
    note: str | None = None


class CreateBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    config: dict


class ContactBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    phone_number: str = Field(min_length=6, max_length=40)
    timezone: str | None = None
    business: str | None = None
    source: str | None = None
    language: str | None = None


class StartCallBody(BaseModel):
    contact_id: str
    agent_version_id: str
    endpoint_id: str | None = None


class BindToolBody(BaseModel):
    revision: int = Field(gt=0)
    binding_key: str = Field(min_length=1, max_length=80, pattern="^[a-z][a-z0-9_]*$")
    tool_version_id: str
    config: dict = Field(default_factory=dict)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "voice-api"}


@app.get("/api/providers")
async def providers(_: None = Operator) -> dict:
    return {
        "providers": [
            {
                "provider": "sarvam",
                "slots": ["stt", "tts"],
                "models": ["saaras:v3", "bulbul:v3"],
            },
            {
                "provider": "groq",
                "slots": ["llm", "classifier", "summarizer"],
                "models": ["qwen/qwen3.8-27b"],
            },
            {"provider": "cartesia", "slots": ["tts"], "models": ["sonic-3"]},
            {
                "provider": "gemini",
                "slots": ["embedding"],
                "models": ["gemini-embedding-001"],
            },
        ]
    }


@app.get("/api/config-schema")
async def config_schema(_: None = Operator) -> dict:
    return {
        "agent": AgentConfig.model_json_schema(),
        "tool": ToolConfig.model_json_schema(),
        "workspace": WorkspaceConfig.model_json_schema(),
    }


async def validate_agent_bindings(session: AsyncSession, version: AgentVersion) -> None:
    """Keep flow JSON references and relational pinned tool versions identical."""
    config = AgentConfig.model_validate(version.config)
    rows = (
        await session.scalars(
            select(AgentVersionTool).where(AgentVersionTool.agent_version_id == version.id)
        )
    ).all()
    database = {row.binding_key: row.tool_version_id for row in rows}
    configured = {key: value.tool_version_id for key, value in config.tool_bindings.items()}
    if database != configured:
        raise HTTPException(422, "Agent tool bindings do not match pinned tool versions")


@app.get("/api/workspace")
async def workspace(session: AsyncSession = Session, _: None = Operator) -> dict:
    row = await session.get(WorkspaceSettings, 1)
    if row is None:
        row = WorkspaceSettings(id=1, config=WorkspaceConfig().model_dump(mode="json"))
        session.add(row)
        await session.commit()
    return {
        "revision": row.revision,
        "config": WorkspaceConfig.model_validate(row.config).model_dump(mode="json"),
    }


@app.patch("/api/workspace")
async def update_workspace(
    body: RevisionBody, session: AsyncSession = Session, _: None = Operator
) -> dict:
    row = await session.get(WorkspaceSettings, 1, with_for_update=True)
    if row is None:
        row = WorkspaceSettings(id=1, revision=1)
        session.add(row)
    if row.revision != body.revision:
        raise HTTPException(409, "Workspace changed by another operator")
    row.config = WorkspaceConfig.model_validate(body.config).model_dump(mode="json")
    row.revision += 1
    await session.commit()
    return {"revision": row.revision, "config": row.config}


@app.get("/api/agents")
async def agents(session: AsyncSession = Session, _: None = Operator) -> dict:
    rows = (await session.scalars(select(Agent).order_by(Agent.name))).all()
    return {
        "agents": [
            {"id": x.id, "name": x.name, "active_version_id": x.active_version_id} for x in rows
        ]
    }


@app.post("/api/agents", status_code=201)
async def create_agent(
    body: CreateBody, session: AsyncSession = Session, _: None = Operator
) -> dict:
    config = AgentConfig.model_validate(body.config).model_dump(mode="json")
    agent = Agent(id=new_id(), name=body.name)
    version = AgentVersion(id=new_id(), agent_id=agent.id, version=1, config=config)
    session.add(agent)
    await session.flush()
    session.add(version)
    await session.flush()
    await sync_bindings(session, version)
    await session.commit()
    return {"agent_id": agent.id, "version_id": version.id}


@app.get("/api/tools")
async def tools(session: AsyncSession = Session, _: None = Operator) -> dict:
    rows = (await session.scalars(select(Tool).order_by(Tool.name))).all()
    return {"tools": [{"id": row.id, "name": row.name} for row in rows]}


@app.post("/api/tools", status_code=201)
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


@app.get("/api/tools/{tool_id}/versions")
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


@app.patch("/api/tool-versions/{version_id}")
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


@app.post("/api/tool-versions/{version_id}/publish")
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


@app.put("/api/agent-versions/{version_id}/tools")
async def bind_tool(
    version_id: str, body: BindToolBody, session: AsyncSession = Session, _: None = Operator
) -> dict:
    agent_version = await session.get(AgentVersion, version_id, with_for_update=True)
    tool_version = await session.get(ToolVersion, body.tool_version_id)
    if agent_version is None or tool_version is None or tool_version.status != "published":
        raise HTTPException(422, "Binding requires draft agent and published tool version")
    if agent_version.status != "draft":
        raise HTTPException(409, "Published agent versions are immutable")
    if agent_version.revision != body.revision:
        raise HTTPException(409, "Draft changed; reload before binding")
    row = await session.get(AgentVersionTool, (version_id, body.binding_key))
    if row is None:
        row = AgentVersionTool(
            agent_version_id=version_id,
            binding_key=body.binding_key,
            tool_version_id=tool_version.id,
            config=body.config,
        )
        session.add(row)
    else:
        row.tool_version_id, row.config = tool_version.id, body.config
    config = AgentConfig.model_validate(agent_version.config).model_dump(mode="json")
    config["tool_bindings"][body.binding_key] = {
        "tool_id": tool_version.tool_id,
        "tool_version_id": tool_version.id,
    }
    agent_version.config = config
    agent_version.revision += 1
    await session.commit()
    return {
        "binding_key": row.binding_key,
        "tool_version_id": row.tool_version_id,
        "revision": agent_version.revision,
    }


@app.get("/api/agents/{agent_id}/versions")
async def agent_versions(
    agent_id: str, session: AsyncSession = Session, _: None = Operator
) -> dict:
    rows = (
        await session.scalars(
            select(AgentVersion)
            .where(AgentVersion.agent_id == agent_id)
            .order_by(AgentVersion.version)
        )
    ).all()
    return {
        "versions": [
            {
                "id": x.id,
                "version": x.version,
                "revision": x.revision,
                "status": x.status,
                "config": x.config,
                "note": x.note,
            }
            for x in rows
        ]
    }


@app.patch("/api/agent-versions/{version_id}")
async def update_agent_version(
    version_id: str, body: RevisionBody, session: AsyncSession = Session, _: None = Operator
) -> dict:
    row = await session.get(AgentVersion, version_id, with_for_update=True)
    if row is None:
        raise HTTPException(404, "Agent version not found")
    if row.status != "draft":
        raise HTTPException(409, "Published versions are immutable")
    if row.revision != body.revision:
        raise HTTPException(409, "Draft changed by another operator")
    row.config = AgentConfig.model_validate(body.config).model_dump(mode="json")
    row.note = body.note
    row.revision += 1
    await sync_bindings(session, row)
    await session.commit()
    return {"id": row.id, "revision": row.revision, "config": row.config}


@app.post("/api/agent-versions/{version_id}/publish")
async def publish_agent(
    version_id: str, body: ExpectedRevision, session: AsyncSession = Session, _: None = Operator
) -> dict:
    row = await session.get(AgentVersion, version_id, with_for_update=True)
    if row is None:
        raise HTTPException(404, "Agent version not found")
    if row.status != "draft":
        raise HTTPException(409, "Version is already published")
    AgentConfig.model_validate(row.config)
    if row.revision != body.revision:
        raise HTTPException(409, "Draft changed; reload before publishing")
    await validate_agent_bindings(session, row)
    row.status = "published"
    row.published_at = datetime.now(UTC)
    await session.commit()
    return {"id": row.id, "status": row.status, "published_at": row.published_at}


@app.post("/api/agents/{agent_id}/activate")
async def activate_agent(
    agent_id: str, body: dict, session: AsyncSession = Session, _: None = Operator
) -> dict:
    agent = await session.get(Agent, agent_id, with_for_update=True)
    version = await session.get(AgentVersion, body.get("version_id"))
    if (
        agent is None
        or version is None
        or version.agent_id != agent_id
        or version.status != "published"
    ):
        raise HTTPException(422, "Select a published agent version")
    agent.active_version_id = version.id
    await session.commit()
    return {"active_version_id": agent.active_version_id}


@app.get("/api/contacts")
async def contacts(session: AsyncSession = Session, _: None = Operator) -> dict:
    rows = (await session.scalars(select(Contact).order_by(Contact.created_at.desc()))).all()
    return {
        "contacts": [
            {
                "id": x.id,
                "name": x.name,
                "phone_number": x.phone_number,
                "timezone": x.timezone,
                "business": x.business,
                "source": x.source,
                "language": x.language,
            }
            for x in rows
        ]
    }


@app.post("/api/contacts", status_code=201)
async def create_contact(
    body: ContactBody, session: AsyncSession = Session, _: None = Operator
) -> dict:
    row = Contact(**body.model_dump())
    session.add(row)
    await session.commit()
    return {"id": row.id}


@app.post("/api/calls", status_code=201)
async def start_call(
    body: StartCallBody, session: AsyncSession = Session, _: None = Operator
) -> dict:
    contact, version = (
        await session.get(Contact, body.contact_id),
        await session.get(AgentVersion, body.agent_version_id),
    )
    if contact is None or version is None or version.status != "published":
        raise HTTPException(422, "Call requires contact and published agent")
    run = Run(
        id=new_id(),
        status="queued",
        agent_version_id=version.id,
        endpoint_id=body.endpoint_id,
        contact_id=contact.id,
        resolved_config=version.config,
        contact_snapshot={"id": contact.id, "name": contact.name, "timezone": contact.timezone},
    )
    call = Call(
        id=new_id(),
        correlation_id=new_id(),
        run_id=run.id,
        contact_id=contact.id,
        agent_version_id=version.id,
        target_snapshot=contact.phone_number,
        status="queued",
    )
    session.add(run)
    await session.flush()
    session.add(call)
    await session.commit()
    return {"run_id": run.id, "call_id": call.id, "status": "queued"}


@app.get("/api/runs/{run_id}/timeline")
async def timeline(run_id: str, session: AsyncSession = Session, _: None = Operator) -> dict:
    run = await session.get(Run, run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    call = await session.scalar(select(Call).where(Call.run_id == run_id))
    exchanges = (
        await session.scalars(
            select(Exchange).where(Exchange.run_id == run_id).order_by(Exchange.sequence)
        )
    ).all()
    ids = [x.id for x in exchanges]
    messages = (
        await session.scalars(
            select(ConversationMessage)
            .where(ConversationMessage.exchange_id.in_(ids))
            .order_by(ConversationMessage.created_at)
            if ids
            else select(ConversationMessage).where(False)
        )
    ).all()
    spans = (
        await session.scalars(
            select(TraceSpan).where(TraceSpan.run_id == run_id).order_by(TraceSpan.started_at)
        )
    ).all()
    tools = (
        await session.scalars(
            select(ToolInvocation)
            .where(ToolInvocation.run_id == run_id)
            .order_by(ToolInvocation.started_at)
        )
    ).all()
    return {
        **await related_evidence(session, run_id),
        "run": {"id": run.id, "status": run.status},
        "call": None if call is None else {"id": call.id, "status": call.status},
        "exchanges": [
            {"id": x.id, "sequence": x.sequence, "origin": x.origin, "status": x.status}
            for x in exchanges
        ],
        "messages": [
            {
                "id": x.id,
                "exchange_id": x.exchange_id,
                "role": x.role,
                "content": x.content,
                "interrupted": x.interrupted,
                "created_at": x.created_at,
            }
            for x in messages
        ],
        "spans": [
            {
                "id": x.id,
                "exchange_id": x.exchange_id,
                "name": x.name,
                "category": x.category,
                "status": x.status,
                "started_at": x.started_at,
                "ended_at": x.ended_at,
                "attributes": x.attributes,
                "provider": x.provider,
                "model": x.model,
                "otel_trace_id": x.otel_trace_id,
                "otel_span_id": x.otel_span_id,
                "duration_ms": x.duration_ms,
                "ttfb_ms": x.ttfb_ms,
                "ttfa_ms": x.ttfa_ms,
                "ttfat_ms": x.ttfat_ms,
                "prompt_tokens": x.prompt_tokens,
                "completion_tokens": x.completion_tokens,
                "reasoning_tokens": x.reasoning_tokens,
                "audio_seconds": x.audio_seconds,
                "input": x.input_payload,
                "output": x.output_payload,
            }
            for x in spans
        ],
        "tools": [
            {
                "id": x.id,
                "exchange_id": x.exchange_id,
                "binding_key": x.binding_key,
                "status": x.status,
                "arguments": x.arguments,
                "result": x.result,
            }
            for x in tools
        ],
    }


dashboard_dist = Path(__file__).resolve().parents[2] / "dashboard" / "dist"
if dashboard_dist.is_dir():
    app.mount("/", StaticFiles(directory=dashboard_dist, html=True), name="dashboard")
