"""Operator-only action-integration configuration and WhatsApp adapter endpoints."""

import hashlib
import re
from datetime import UTC, datetime
from secrets import compare_digest
from typing import Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from voice_api.api.deps import get_session, require_operator
from voice_api.core.config import get_settings
from voice_api.models import (
    AgentVersion,
    AgentVersionTool,
    InboundWebhookMessage,
    IntegrationConnection,
    IntegrationMedia,
    IntegrationSecret,
    Run,
    Tool,
    ToolInvocation,
    ToolVersion,
)
from voice_api.models.common import new_id, now
from voice_api.schemas.integrations import (
    ConnectionBody,
    GeneratedTemplateToolResponse,
    GenerateTemplateToolBody,
    MediaImportBody,
    MediaListResponse,
    MediaResponse,
    MediaUpdateBody,
    SecretBody,
    UpdateConnectionBody,
)
from voice_api.services.vault_service import CredentialVault, VaultError
from voice_api.services.whatsapp_service import WhatsAppAdapter, _inbound_window, verify_signature

router = APIRouter(tags=["integrations"])
Session = Depends(get_session)

Operator = Depends(require_operator)
MAX_WHATSAPP_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_WHATSAPP_IMAGE_TYPES = {"image/png", "image/jpeg"}


def webhook_url(connection_id: str) -> str | None:
    base = get_settings().public_base_url
    if not base:
        return None
    return f"{base.rstrip('/')}/api/v1/integrations/whatsapp/{connection_id}/webhook"


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
        "deleted_at": connection.deleted_at.isoformat() if connection.deleted_at else None,
        "webhook_url": webhook_url(connection.id),
    }


def media_response(row: IntegrationMedia) -> MediaResponse:
    return MediaResponse(
        id=row.id,
        connection_id=row.connection_id,
        provider_media_id=row.provider_media_id,
        display_name=row.display_name,
        filename=row.filename,
        media_type=row.media_type,
        mime_type=row.mime_type,
        size_bytes=row.size_bytes,
        sha256=row.sha256,
        source=row.source,
        status=row.status,
        provider_metadata=row.provider_metadata,
        uploaded_at=row.uploaded_at,
        last_verified_at=row.last_verified_at,
    )


def media_type_for_mime(mime_type: str) -> str:
    if mime_type.startswith("image/"):
        return "image"
    if mime_type.startswith("video/"):
        return "video"
    if mime_type.startswith("audio/"):
        return "audio"
    return "document"


def safe_media_metadata(payload: dict[str, Any], *, provider_media_id: str) -> dict[str, Any]:
    """Keep only non-secret, stable fields from Meta media responses."""

    allowed = {"id", "mime_type", "sha256", "file_size", "messaging_product"}
    result = {key: value for key, value in payload.items() if key in allowed}
    result["id"] = provider_media_id
    return result


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
    if body.provider == "whatsapp":
        existing_active = await session.scalar(
            select(IntegrationConnection).where(
                IntegrationConnection.provider == "whatsapp",
                IntegrationConnection.deleted_at.is_(None),
            )
        )
        if existing_active:
            raise HTTPException(409, "Only one active WhatsApp integration connection is permitted")
    row = IntegrationConnection(id=new_id(), **body.model_dump())
    session.add(row)
    await session.commit()
    return summary(row, secret_names=[])


@router.post("/integrations/{connection_id}/disconnect")
async def disconnect_connection(
    connection_id: str,
    session: AsyncSession = Session,
    _: None = Operator,
) -> dict:
    connection = await connection_or_404(session, connection_id)
    # Remove secrets
    await session.execute(
        delete(IntegrationSecret).where(IntegrationSecret.connection_id == connection_id)
    )
    # Mark disabled and set deleted_at
    connection.enabled = False
    connection.deleted_at = now()
    config = dict(connection.config or {})
    config["status"] = "disconnected"
    connection.config = config
    connection.updated_at = now()
    await session.commit()
    return summary(connection, secret_names=[])


@router.delete("/integrations/{connection_id}")
async def delete_connection(
    connection_id: str,
    session: AsyncSession = Session,
    _: None = Operator,
) -> dict:
    connection = await connection_or_404(session, connection_id)
    await session.execute(text("SET LOCAL session_replication_role = 'replica';"))

    # If WhatsApp, find and delete associated WhatsApp template and message tools
    if connection.provider == "whatsapp":
        tools = (
            await session.scalars(
                select(Tool).where(
                    (Tool.name.like("whatsapp_template_%"))
                    | (Tool.name == "send_whatsapp_message")
                    | (Tool.name == "send_whatsapp_template")
                )
            )
        ).all()
        for t in tools:
            tv_ids = (
                await session.scalars(select(ToolVersion.id).where(ToolVersion.tool_id == t.id))
            ).all()
            if tv_ids:
                await session.execute(
                    delete(AgentVersionTool).where(AgentVersionTool.tool_version_id.in_(tv_ids))
                )
                await session.execute(delete(ToolVersion).where(ToolVersion.tool_id == t.id))

            # Clean tool references in agent configs
            agent_versions = (await session.scalars(select(AgentVersion))).all()
            for av in agent_versions:
                cfg = dict(av.config or {})
                tb = dict(cfg.get("tool_bindings", {}))
                changed = False
                if t.name in tb:
                    del tb[t.name]
                    changed = True
                flow = dict(cfg.get("flow", {}))
                nodes = list(flow.get("nodes", []))
                for n in nodes:
                    node_tools = n.get("tool_bindings", [])
                    if isinstance(node_tools, list) and t.name in node_tools:
                        n["tool_bindings"] = [x for x in node_tools if x != t.name]
                        changed = True
                if changed:
                    cfg["tool_bindings"] = tb
                    flow["nodes"] = nodes
                    cfg["flow"] = flow
                    av.config = cfg

            await session.execute(delete(Tool).where(Tool.id == t.id))

    # Delete integration secrets, media, inbound messages
    await session.execute(
        delete(IntegrationSecret).where(IntegrationSecret.connection_id == connection_id)
    )
    await session.execute(
        delete(IntegrationMedia).where(IntegrationMedia.connection_id == connection_id)
    )
    await session.execute(
        delete(InboundWebhookMessage).where(InboundWebhookMessage.connection_id == connection_id)
    )
    await session.execute(
        delete(IntegrationConnection).where(IntegrationConnection.id == connection_id)
    )
    await session.commit()
    return {"status": "ok", "deleted_connection_id": connection_id, "label": connection.label}


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
            if connection.provider == "twilio_voice":
                required = {"auth_token"}
            else:
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
    if name not in {"access_token", "app_secret", "verify_token", "auth_token"}:
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


@router.post("/integrations/{connection_id}/test")
async def test_connection_endpoint(
    connection_id: str,
    session: AsyncSession = Session,
    _: None = Operator,
) -> dict:
    connection = await connection_or_404(session, connection_id)
    if connection.provider == "twilio_voice":
        from voice_api.services.twilio_service import (
            resolve_twilio_credentials,
            test_twilio_connection,
        )

        _, credentials = await resolve_twilio_credentials(
            session, connection_id, require_enabled=False
        )
        return await test_twilio_connection(credentials)
    raise HTTPException(422, f"Test connection not supported for {connection.provider}")


@router.post("/integrations/{connection_id}/refresh-numbers")
async def refresh_numbers_endpoint(
    connection_id: str,
    session: AsyncSession = Session,
    _: None = Operator,
) -> dict:
    connection = await connection_or_404(session, connection_id)
    if connection.provider != "twilio_voice":
        raise HTTPException(422, "Only Twilio connections support phone number refresh")
    from voice_api.services.twilio_service import sync_twilio_phone_numbers

    result = await sync_twilio_phone_numbers(session, connection_id)
    return result


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


@router.get("/integrations/{connection_id}/media", response_model=MediaListResponse)
async def list_media(
    connection_id: str,
    session: AsyncSession = Session,
    _: None = Operator,
) -> MediaListResponse:
    await connection_or_404(session, connection_id)
    rows = (
        await session.scalars(
            select(IntegrationMedia)
            .where(IntegrationMedia.connection_id == connection_id)
            .order_by(IntegrationMedia.uploaded_at.desc())
        )
    ).all()
    return MediaListResponse(media=[media_response(row) for row in rows])


def _validate_template_parameter_mappings(
    parameter_mappings: dict[str, str],
    template_indexes: set[str],
    tool_argument_names: set[str],
) -> None:
    unknown_template_indexes = set(parameter_mappings) - template_indexes
    if unknown_template_indexes:
        raise HTTPException(
            422,
            "Parameter mappings reference unknown template placeholders: "
            f"{sorted(unknown_template_indexes)}",
        )

    unknown_argument_names = set(parameter_mappings.values()) - tool_argument_names
    if unknown_argument_names:
        raise HTTPException(
            422,
            f"Parameter mappings reference unknown tool arguments: {sorted(unknown_argument_names)}",
        )


@router.post(
    "/integrations/{connection_id}/media/import",
    status_code=201,
    response_model=MediaResponse,
)
async def import_media(
    connection_id: str,
    body: MediaImportBody,
    session: AsyncSession = Session,
    _: None = Operator,
) -> MediaResponse:
    connection = await connection_or_404(session, connection_id)
    if connection.provider != "whatsapp":
        raise HTTPException(422, "Media catalog is available only for WhatsApp connections")
    existing = await session.scalar(
        select(IntegrationMedia).where(
            IntegrationMedia.connection_id == connection_id,
            IntegrationMedia.provider_media_id == body.provider_media_id,
        )
    )
    if existing is not None:
        raise HTTPException(409, "This provider media ID is already in the catalog")
    row = IntegrationMedia(
        id=new_id(),
        connection_id=connection_id,
        provider_media_id=body.provider_media_id,
        display_name=body.display_name,
        filename=body.original_filename or body.display_name,
        media_type=body.media_type,
        mime_type=body.mime_type,
        size_bytes=body.size_bytes,
        sha256=body.sha256,
        source="imported",
        status="unverified",
        provider_metadata=safe_media_metadata(
            body.provider_metadata, provider_media_id=body.provider_media_id
        ),
    )
    session.add(row)
    await session.commit()
    return media_response(row)


@router.post(
    "/integrations/{connection_id}/media/upload",
    status_code=201,
    response_model=MediaResponse,
)
async def upload_media(
    connection_id: str,
    file: UploadFile,
    display_name: str | None = Form(default=None),
    session: AsyncSession = Session,
    _: None = Operator,
) -> MediaResponse:
    connection = await connection_or_404(session, connection_id)
    if connection.provider != "whatsapp" or not connection.enabled:
        raise HTTPException(422, "An enabled WhatsApp connection is required")
    content = await file.read(MAX_WHATSAPP_IMAGE_BYTES + 1)
    await file.close()
    if not content or len(content) > MAX_WHATSAPP_IMAGE_BYTES:
        raise HTTPException(422, "Image must be between 1 byte and 5 MiB")
    mime_type = (file.content_type or "").lower().split(";", 1)[0]
    signatures = {
        "image/png": content.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/jpeg": content.startswith(b"\xff\xd8\xff"),
    }
    if mime_type not in ALLOWED_WHATSAPP_IMAGE_TYPES or not signatures[mime_type]:
        raise HTTPException(422, "Only valid PNG and JPEG images can be uploaded")
    filename = (file.filename or "upload").replace("\\", "/").rsplit("/", 1)[-1]
    display_name = (display_name or filename).strip()
    if not display_name or len(display_name) > 255:
        raise HTTPException(422, "Display name must be between 1 and 255 characters")
    adapter = await whatsapp(session, connection)
    async with adapter:
        provider = await adapter.upload_media(filename, mime_type, content)
    provider_media_id = provider.get("id")
    if not isinstance(provider_media_id, str):
        raise HTTPException(502, "WhatsApp did not return a media ID")
    digest = hashlib.sha256(content).hexdigest()
    row = IntegrationMedia(
        id=new_id(),
        connection_id=connection_id,
        provider_media_id=provider_media_id,
        filename=filename,
        display_name=display_name,
        media_type="image",
        mime_type=mime_type,
        size_bytes=len(content),
        sha256=digest,
        source="uploaded",
        status="available",
        provider_metadata=safe_media_metadata(provider, provider_media_id=provider_media_id),
        last_verified_at=now(),
    )
    session.add(row)
    await session.commit()
    return media_response(row)


def _whatsapp_config_references_media(
    config: Any, *, connection_id: str, media: IntegrationMedia
) -> bool:
    if not isinstance(config, dict) or config.get("connection_id") != connection_id:
        return False
    header = config.get("header")
    provider_id = header.get("media_id") if isinstance(header, dict) else None
    references = (provider_id, config.get("header_media_id"))
    return any(
        isinstance(value, str) and value in (media.id, media.provider_media_id)
        for value in references
    )


def _snapshot_references_media(
    snapshot: dict, *, connection_id: str, media: IntegrationMedia
) -> bool:
    resolved = snapshot.get("_resolved", {})
    tools = resolved.get("tools", {}) if isinstance(resolved, dict) else {}
    if not isinstance(tools, dict):
        return False
    for tool in tools.values():
        definition = tool.get("definition", {}) if isinstance(tool, dict) else {}
        config = definition.get("whatsapp", {}) if isinstance(definition, dict) else {}
        if _whatsapp_config_references_media(config, connection_id=connection_id, media=media):
            return True
    return False


@router.get(
    "/integrations/{connection_id}/media/{media_id}/preview",
    response_class=Response,
    responses={
        200: {
            "description": "Meta-hosted PNG or JPEG image bytes (not persisted)",
            "content": {
                "image/png": {"schema": {"type": "string", "format": "binary"}},
                "image/jpeg": {"schema": {"type": "string", "format": "binary"}},
            },
        }
    },
)
async def preview_media(
    connection_id: str,
    media_id: str,
    session: AsyncSession = Session,
    _: None = Operator,
) -> Response:
    connection = await connection_or_404(session, connection_id)
    media = await session.scalar(
        select(IntegrationMedia).where(
            IntegrationMedia.id == media_id,
            IntegrationMedia.connection_id == connection_id,
            IntegrationMedia.media_type == "image",
            IntegrationMedia.status == "available",
        )
    )
    if media is None:
        raise HTTPException(404, "Available image media record not found")
    adapter = await whatsapp(session, connection)
    try:
        async with adapter:
            content, mime_type = await adapter.preview_image(
                media.provider_media_id, max_bytes=MAX_WHATSAPP_IMAGE_BYTES
            )
    except Exception as error:
        raise HTTPException(502, "Meta image preview is unavailable") from error
    return Response(
        content,
        media_type=mime_type,
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.delete("/integrations/{connection_id}/media/{media_id}", status_code=204)
async def delete_media(
    connection_id: str,
    media_id: str,
    session: AsyncSession = Session,
    _: None = Operator,
) -> None:
    connection = await connection_or_404(session, connection_id)
    media = await session.scalar(
        select(IntegrationMedia)
        .where(
            IntegrationMedia.id == media_id,
            IntegrationMedia.connection_id == connection_id,
        )
        .with_for_update()
    )
    if media is None:
        raise HTTPException(404, "Media record not found")
    versions = (await session.scalars(select(ToolVersion))).all()
    if any(
        _whatsapp_config_references_media(
            version.config.get("whatsapp") if isinstance(version.config, dict) else None,
            connection_id=connection_id,
            media=media,
        )
        for version in versions
    ):
        raise HTTPException(
            409, "Replace or remove all tool-version references before deleting media"
        )
    runs = (
        await session.scalars(
            select(Run).where(Run.status.in_(("queued", "claimed", "running", "uncertain")))
        )
    ).all()
    if any(
        isinstance(run.resolved_config, dict)
        and _snapshot_references_media(
            run.resolved_config, connection_id=connection_id, media=media
        )
        for run in runs
    ):
        raise HTTPException(409, "An executable run snapshot still references this media")
    adapter = await whatsapp(session, connection)
    try:
        async with adapter:
            await adapter.delete_media(media.provider_media_id)
    except Exception as error:
        raise HTTPException(502, "Meta did not confirm media deletion") from error
    await session.delete(media)
    await session.commit()


@router.patch("/integrations/{connection_id}/media/{media_id}", response_model=MediaResponse)
async def update_media(
    connection_id: str,
    media_id: str,
    body: MediaUpdateBody,
    session: AsyncSession = Session,
    _: None = Operator,
) -> MediaResponse:
    await connection_or_404(session, connection_id)
    row = await session.scalar(
        select(IntegrationMedia).where(
            IntegrationMedia.id == media_id,
            IntegrationMedia.connection_id == connection_id,
        )
    )
    if row is None:
        raise HTTPException(404, "Media record not found")
    row.display_name = body.display_name.strip()
    await session.commit()
    return media_response(row)


@router.post("/integrations/{connection_id}/media/{media_id}/verify", response_model=MediaResponse)
async def verify_media(
    connection_id: str,
    media_id: str,
    session: AsyncSession = Session,
    _: None = Operator,
) -> MediaResponse:
    connection = await connection_or_404(session, connection_id)
    row = await session.scalar(
        select(IntegrationMedia).where(
            IntegrationMedia.id == media_id,
            IntegrationMedia.connection_id == connection_id,
        )
    )
    if row is None:
        raise HTTPException(404, "Media record not found")
    adapter = await whatsapp(session, connection)
    async with adapter:
        provider = await adapter.check_media(row.provider_media_id)
    row.status = "available"
    row.last_verified_at = now()
    row.provider_metadata = safe_media_metadata(provider, provider_media_id=row.provider_media_id)
    if isinstance(provider.get("mime_type"), str):
        row.mime_type = provider["mime_type"]
        row.media_type = media_type_for_mime(row.mime_type)
    if isinstance(provider.get("file_size"), int):
        row.size_bytes = provider["file_size"]
    if isinstance(provider.get("sha256"), str) and re.fullmatch(
        r"[a-f0-9]{64}", provider["sha256"]
    ):
        row.sha256 = provider["sha256"]
    await session.commit()
    return media_response(row)


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


@router.post(
    "/integrations/{connection_id}/generate-template-tool",
    status_code=201,
    response_model=GeneratedTemplateToolResponse,
)
async def generate_template_tool(
    connection_id: str,
    body: GenerateTemplateToolBody,
    session: AsyncSession = Session,
    _: None = Operator,
) -> GeneratedTemplateToolResponse:
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

    for key, value in body.parameter_descriptions.items():
        if key in properties and value.strip():
            properties[key]["description"] = value.strip()

    header_media_id = body.header_media_id
    header_config = None
    header_component = next(
        (c for c in match.get("components", []) if c.get("type") == "HEADER"), None
    )
    allowed_header_formats = {"IMAGE", "VIDEO", "DOCUMENT"}
    template_header_format = (
        str(header_component.get("format", "")).upper() if header_component else None
    )
    if header_media_id and template_header_format not in allowed_header_formats:
        raise HTTPException(422, "This template does not accept media in its header")
    if header_media_id:
        media = await session.scalar(
            select(IntegrationMedia)
            .where(
                IntegrationMedia.connection_id == connection_id,
                IntegrationMedia.provider_media_id == header_media_id,
                IntegrationMedia.status == "available",
            )
            .with_for_update()
        )
        if media is None:
            raise HTTPException(422, "Selected header media is not available for this integration")
        expected_type = {
            "IMAGE": "image",
            "VIDEO": "video",
            "DOCUMENT": "document",
        }.get(template_header_format or "")
        if expected_type and media.media_type != expected_type:
            raise HTTPException(
                422,
                f"Selected media is type '{media.media_type}', but this template requires '{expected_type}'",
            )
        format_by_type = {"image": "IMAGE", "video": "VIDEO", "document": "DOCUMENT"}
        header_format = format_by_type.get(media.media_type)
        if header_format is None:
            raise HTTPException(422, "Selected media type cannot be used as a template header")
        header_config = {"format": header_format, "media_id": media.provider_media_id}
    if template_header_format in allowed_header_formats and not header_media_id:
        raise HTTPException(422, "This template requires a matching header media record")
    description = (
        body.description
        or f"Send approved WhatsApp template '{match.get('name')}' ({match.get('language')}) via {connection.label}."
    )

    parameter_mappings = dict(body.parameter_mappings)
    if not parameter_mappings:
        template_indexes = (
            re.findall(r"\{\{(\d+)\}\}", body_component.get("text", "")) if body_component else []
        )
        if len(template_indexes) == 1:
            parameter_mappings = {template_indexes[0]: "message"}
        else:
            parameter_mappings = {
                index: ("caller_name" if index == "1" else f"param_{index}")
                for index in sorted(set(template_indexes))
            }

    template_indexes = (
        set(re.findall(r"\{\{(\d+)\}\}", body_component.get("text", "")))
        if body_component
        else set()
    )
    _validate_template_parameter_mappings(parameter_mappings, template_indexes, set(properties))

    config = {
        "name": tool_name,
        "description": description,
        "kind": "registered",
        "handler": "send_whatsapp_template",
        "whatsapp": {
            "connection_id": connection_id,
            "template_name": match.get("name"),
            "language": match.get("language") or body.language,
            "header": header_config,
            "parameter_mappings": parameter_mappings,
        },
        "parameters": {
            "type": "object",
            "properties": properties,
        },
        "wait": {"mode": "silent_wait"},
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
    extracted_variables = sorted({key for key in properties if key not in {"caller_name", "to"}})
    return GeneratedTemplateToolResponse(
        tool_id=tool.id,
        tool_version_id=version.id,
        name=tool.name,
        tool_name=tool.name,
        version=version.version,
        version_number=version.version,
        extracted_variables=extracted_variables,
        config=version.config,
    )


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
                from_raw = str(message.get("from") or "")
                sender_phone = re.sub(r"[^\d]", "", from_raw)
                if sender_phone:
                    ts = message.get("timestamp")
                    try:
                        received_dt = datetime.fromtimestamp(int(ts), UTC) if ts else now()
                    except Exception:
                        received_dt = now()
                    inbound_row = InboundWebhookMessage(
                        id=new_id(),
                        connection_id=connection_id,
                        sender_phone=sender_phone,
                        provider_message_id=message.get("id"),
                        payload=message,
                        received_at=received_dt,
                    )
                    session.add(inbound_row)
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
