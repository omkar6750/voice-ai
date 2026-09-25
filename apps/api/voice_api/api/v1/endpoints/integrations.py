"""Operator-only action-integration configuration and WhatsApp adapter endpoints."""

import hashlib
import re
from pathlib import Path
from secrets import compare_digest
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from voice_api.api.deps import get_session, require_operator
from voice_api.core.config import get_settings
from voice_api.models import (
    IntegrationConnection,
    IntegrationMedia,
    IntegrationSecret,
    Tool,
    ToolInvocation,
    ToolVersion,
)
from voice_api.models.common import new_id, now
from voice_api.schemas.integrations import (
    ConnectionBody,
    GenerateTemplateToolBody,
    MediaImportBody,
    SecretBody,
    UpdateConnectionBody,
)
from voice_api.services.vault_service import CredentialVault, VaultError
from voice_api.services.whatsapp_service import WhatsAppAdapter, _inbound_window, verify_signature

router = APIRouter(tags=["integrations"])
Session = Depends(get_session)

Operator = Depends(require_operator)


def summary(connection: IntegrationConnection, *, secret_names: list[str]) -> dict:
    return {
        "id": connection.id,
        "label": connection.label,
        "provider": connection.provider,
        "config": connection.config,
        "enabled": connection.enabled,
        "secret_names": secret_names,
        "updated_at": connection.updated_at.isoformat() if connection.updated_at else None,
        "created_at": connection.created_at.isoformat() if connection.created_at else None,
    }


async def connection_or_404(session: AsyncSession, connection_id: str) -> IntegrationConnection:
    connection = await session.get(IntegrationConnection, connection_id)
    if connection is None:
        raise HTTPException(404, "Integration connection not found")
    return connection


async def secret_value(session: AsyncSession, connection_id: str, name: str) -> str:
    secret = await session.scalar(
        select(IntegrationSecret).where(
            IntegrationSecret.connection_id == connection_id,
            IntegrationSecret.name == name,
        )
    )
    if secret is None:
        raise HTTPException(422, f"Connection is missing {name}")
    try:
        return CredentialVault.from_env().decrypt(secret.ciphertext, secret.key_id)
    except VaultError as error:
        raise HTTPException(503, "Integration credential is unavailable") from error


async def whatsapp(session: AsyncSession, connection: IntegrationConnection) -> WhatsAppAdapter:
    if connection.provider != "whatsapp":
        raise HTTPException(422, "Connection is not WhatsApp")
    config = connection.config
    try:
        return WhatsAppAdapter(
            await secret_value(session, connection.id, "access_token"),
            str(config["phone_number_id"]),
            str(config["waba_id"]),
            str(config.get("api_version", "v23.0")),
        )
    except (KeyError, ValueError) as error:
        raise HTTPException(422, "Invalid WhatsApp connection configuration") from error


@router.get("/integrations")
async def list_connections(session: AsyncSession = Session, _: None = Operator) -> dict:
    connections = (
        await session.scalars(select(IntegrationConnection).order_by(IntegrationConnection.label))
    ).all()
    secret_rows = (await session.scalars(select(IntegrationSecret))).all()
    names: dict[str, list[str]] = {}
    for secret in secret_rows:
        names.setdefault(secret.connection_id, []).append(secret.name)
    return {
        "connections": [summary(row, secret_names=names.get(row.id, [])) for row in connections]
    }


@router.post("/integrations", status_code=201)
async def create_connection(
    body: ConnectionBody,
    session: AsyncSession = Session,
    _: None = Operator,
) -> dict:
    row = IntegrationConnection(id=new_id(), **body.model_dump())
    session.add(row)
    await session.commit()
    return summary(row, secret_names=[])


@router.get("/integrations/{connection_id}")
async def get_connection(
    connection_id: str,
    session: AsyncSession = Session,
    _: None = Operator,
) -> dict:
    connection = await connection_or_404(session, connection_id)
    secret_rows = (
        await session.scalars(
            select(IntegrationSecret).where(IntegrationSecret.connection_id == connection_id)
        )
    ).all()
    return summary(connection, secret_names=[s.name for s in secret_rows])


@router.patch("/integrations/{connection_id}")
async def update_connection(
    connection_id: str,
    body: UpdateConnectionBody,
    session: AsyncSession = Session,
    _: None = Operator,
) -> dict:
    connection = await session.get(IntegrationConnection, connection_id, with_for_update=True)
    if connection is None:
        raise HTTPException(404, "Integration connection not found")
    if body.expected_updated_at and connection.updated_at:
        if connection.updated_at.isoformat() != body.expected_updated_at:
            raise HTTPException(409, "Connection was modified by another operator")
    if body.label is not None and body.label != connection.label:
        existing = await session.scalar(
            select(IntegrationConnection).where(
                IntegrationConnection.label == body.label,
                IntegrationConnection.id != connection_id,
            )
        )
        if existing:
            raise HTTPException(409, "Connection label already in use")
        connection.label = body.label
    if body.config is not None:
        connection.config = body.config.model_dump(mode="json")
    if body.enabled is not None:
        if body.enabled:
            secret_rows = (
                await session.scalars(
                    select(IntegrationSecret).where(
                        IntegrationSecret.connection_id == connection_id
                    )
                )
            ).all()
            secret_names = {s.name for s in secret_rows}
            required = {"access_token"}
            missing = required - secret_names
            if missing:
                raise HTTPException(
                    422, f"Cannot enable connection without secrets: {', '.join(sorted(missing))}"
                )
        connection.enabled = body.enabled
    connection.updated_at = now()
    await session.commit()

    secret_rows = (
        await session.scalars(
            select(IntegrationSecret).where(IntegrationSecret.connection_id == connection_id)
        )
    ).all()
    return summary(connection, secret_names=[s.name for s in secret_rows])


@router.put("/integrations/{connection_id}/secrets/{name}", status_code=204)
async def put_secret(
    connection_id: str,
    name: str,
    body: SecretBody,
    session: AsyncSession = Session,
    _: None = Operator,
) -> None:
    await connection_or_404(session, connection_id)
    if name not in {"access_token", "app_secret", "verify_token"}:
        raise HTTPException(422, "Unsupported integration secret name")
    try:
        encrypted = CredentialVault.from_env().encrypt(body.value)
    except VaultError as error:
        raise HTTPException(503, "Integration encryption is not configured") from error
    row = await session.scalar(
        select(IntegrationSecret).where(
            IntegrationSecret.connection_id == connection_id, IntegrationSecret.name == name
        )
    )
    if row is None:
        row = IntegrationSecret(
            id=new_id(), connection_id=connection_id, name=name, **encrypted.__dict__
        )
        session.add(row)
    else:
        row.ciphertext, row.key_id = encrypted.ciphertext, encrypted.key_id
    await session.commit()


@router.post("/integrations/{connection_id}/rotate-secrets", status_code=204)
async def rotate_secrets(
    connection_id: str,
    session: AsyncSession = Session,
    _: None = Operator,
) -> None:
    await connection_or_404(session, connection_id)
    try:
        vault = CredentialVault.from_env()
        rows = (
            await session.scalars(
                select(IntegrationSecret).where(IntegrationSecret.connection_id == connection_id)
            )
        ).all()
        for row in rows:
            rotated = vault.rotate(row.ciphertext, row.key_id)
            row.ciphertext, row.key_id = rotated.ciphertext, rotated.key_id
    except VaultError as error:
        raise HTTPException(503, "Integration credential rotation failed") from error
    await session.commit()


@router.get("/integrations/{connection_id}/media")
async def list_media(
    connection_id: str,
    session: AsyncSession = Session,
    _: None = Operator,
) -> dict:
    await connection_or_404(session, connection_id)
    rows = (
        await session.scalars(
            select(IntegrationMedia)
            .where(IntegrationMedia.connection_id == connection_id)
            .order_by(IntegrationMedia.uploaded_at.desc())
        )
    ).all()
    return {
        "media": [
            {
                "id": row.id,
                "provider_media_id": row.provider_media_id,
                "filename": row.filename,
                "mime_type": row.mime_type,
                "size_bytes": row.size_bytes,
                "sha256": row.sha256,
                "availability": row.availability,
            }
            for row in rows
        ]
    }


@router.post("/integrations/{connection_id}/media/import", status_code=201)
async def import_media(
    connection_id: str,
    body: MediaImportBody,
    session: AsyncSession = Session,
    _: None = Operator,
) -> dict:
    await connection_or_404(session, connection_id)
    row = IntegrationMedia(id=new_id(), connection_id=connection_id, **body.model_dump())
    session.add(row)
    await session.commit()
    return {"id": row.id, "availability": row.availability}


@router.post("/integrations/{connection_id}/media/upload", status_code=201)
async def upload_media(
    connection_id: str,
    file: UploadFile,
    session: AsyncSession = Session,
    _: None = Operator,
) -> dict:
    connection = await connection_or_404(session, connection_id)
    content = await file.read()
    if not content or len(content) > 16 * 1024 * 1024:
        raise HTTPException(422, "Media must be between 1 byte and 16 MiB")
    filename = Path(file.filename or "upload").name
    mime_type = file.content_type or "application/octet-stream"
    adapter = await whatsapp(session, connection)
    async with adapter:
        provider = await adapter.upload_media(filename, mime_type, content)
    provider_media_id = provider.get("id")
    if not isinstance(provider_media_id, str):
        raise HTTPException(502, "WhatsApp did not return a media ID")
    digest = hashlib.sha256(content).hexdigest()
    directory = Path(get_settings().integration_media_dir) / connection_id
    directory.mkdir(parents=True, exist_ok=True)
    source_path = directory / f"{digest}-{filename}"
    source_path.write_bytes(content)
    row = IntegrationMedia(
        id=new_id(),
        connection_id=connection_id,
        provider_media_id=provider_media_id,
        filename=filename,
        mime_type=mime_type,
        size_bytes=len(content),
        sha256=digest,
        source_path=str(source_path),
    )
    session.add(row)
    await session.commit()
    return {"id": row.id, "provider_media_id": row.provider_media_id, "sha256": row.sha256}


@router.get("/integrations/{connection_id}/templates")
async def templates(
    connection_id: str,
    session: AsyncSession = Session,
    _: None = Operator,
) -> dict:
    connection = await connection_or_404(session, connection_id)
    adapter = await whatsapp(session, connection)
    async with adapter:
        return {"templates": await adapter.template_catalog()}


@router.post("/integrations/{connection_id}/generate-template-tool", status_code=201)
async def generate_template_tool(
    connection_id: str,
    body: GenerateTemplateToolBody,
    session: AsyncSession = Session,
    _: None = Operator,
) -> dict:
    connection = await connection_or_404(session, connection_id)
    adapter = await whatsapp(session, connection)
    async with adapter:
        meta_templates = await adapter.template_catalog()

    match = None
    for tmpl in meta_templates:
        if tmpl.get("name") == body.template_name:
            if not body.language or tmpl.get("language") == body.language:
                match = tmpl
                break
    if match is None:
        raise HTTPException(
            404, f"Template '{body.template_name}' not found on Meta for this WhatsApp account"
        )

    # Sanitize tool name: whatsapp_template_<sanitized_name>
    sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", body.template_name.lower())
    tool_name = (body.tool_name or f"whatsapp_template_{sanitized}").strip()

    # Analyze components to extract parameters
    properties: dict[str, Any] = {
        "caller_name": {
            "type": "string",
            "description": "Recipient name for template greeting or parameter substitution",
        },
        "to": {
            "type": "string",
            "description": "Optional destination international phone number (defaults to contact's phone)",
        },
    }

    body_component = next((c for c in match.get("components", []) if c.get("type") == "BODY"), None)
    if body_component:
        text = body_component.get("text", "")
        placeholders = re.findall(r"\{\{(\d+)\}\}", text)
        if len(placeholders) > 1:
            for idx in sorted(set(placeholders)):
                var_name = "caller_name" if idx == "1" else f"param_{idx}"
                if var_name not in properties:
                    properties[var_name] = {
                        "type": "string",
                        "description": f"Template variable {{{{{idx}}}}}",
                    }
        elif len(placeholders) == 1:
            properties["message"] = {
                "type": "string",
                "description": "Template body text or follow-up note",
            }

    description = (
        body.description
        or f"Send approved WhatsApp template '{match.get('name')}' ({match.get('language')}) via {connection.label}."
    )

    config = {
        "name": tool_name,
        "description": description,
        "kind": "registered",
        "handler": "send_whatsapp_template",
        "parameters": {
            "type": "object",
            "properties": properties,
        },
        "wait": {
            "mode": "acknowledge_then_wait",
            "acknowledgement": "I'm sending that to your WhatsApp right now.",
        },
    }

    existing_tool = await session.scalar(select(Tool).where(Tool.name == tool_name))
    if existing_tool is None:
        tool = Tool(id=new_id(), name=tool_name)
        session.add(tool)
        await session.flush()
        version = ToolVersion(id=new_id(), tool_id=tool.id, version=1, config=config)
        session.add(version)
    else:
        tool = existing_tool
        latest_version = (
            await session.scalar(
                select(func.max(ToolVersion.version)).where(ToolVersion.tool_id == tool.id)
            )
            or 0
        )
        version = ToolVersion(
            id=new_id(), tool_id=tool.id, version=latest_version + 1, config=config
        )
        session.add(version)

    await session.commit()
    return {
        "tool_id": tool.id,
        "tool_version_id": version.id,
        "name": tool.name,
        "version": version.version,
        "config": version.config,
    }


@router.get("/integrations/whatsapp/{connection_id}/webhook")
async def verify_webhook(
    connection_id: str,
    request: Request,
    session: AsyncSession = Session,
) -> PlainTextResponse:
    await connection_or_404(session, connection_id)
    verify = await secret_value(session, connection_id, "verify_token")
    if request.query_params.get("hub.mode") != "subscribe" or not compare_digest(
        request.query_params.get("hub.verify_token", "").encode(), verify.encode()
    ):
        raise HTTPException(403, "Webhook verification failed")
    return PlainTextResponse(request.query_params.get("hub.challenge", ""))


@router.post("/integrations/whatsapp/{connection_id}/webhook", status_code=204)
async def receive_webhook(
    connection_id: str, request: Request, session: AsyncSession = Session
) -> None:
    connection = await connection_or_404(session, connection_id)
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    app_secret = await secret_value(session, connection_id, "app_secret")
    if not verify_signature(body, signature, app_secret):
        raise HTTPException(403, "Webhook signature failed")
    payload = await request.json()
    for entry in payload.get("entry", []):
        if str(entry.get("id")) != str(connection.config.get("waba_id")):
            continue
        for change in entry.get("changes", []):
            value = change.get("value", {})
            if str(value.get("metadata", {}).get("phone_number_id")) != str(
                connection.config.get("phone_number_id")
            ):
                continue
            for message in value.get("messages", []):
                _inbound_window.observe(
                    connection_id, message.get("from"), message.get("timestamp")
                )
            for status in value.get("statuses", []):
                message_id = status.get("id")
                if not isinstance(message_id, str):
                    continue
                invocation = await session.scalar(
                    select(ToolInvocation)
                    .where(
                        ToolInvocation.provider_message_id == message_id,
                        ToolInvocation.connection_id == connection_id,
                    )
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
                if invocation is not None:
                    receipt = {key: value for key, value in status.items() if key != "conversation"}
                    identity = (receipt.get("id"), receipt.get("status"), receipt.get("timestamp"))
                    if not any(
                        (r.get("id"), r.get("status"), r.get("timestamp")) == identity
                        for r in invocation.receipts
                    ):
                        invocation.receipts = [*invocation.receipts, receipt]
    await session.commit()
