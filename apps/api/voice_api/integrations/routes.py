"""Operator-only action-integration configuration and WhatsApp adapter endpoints."""

import hashlib
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from voice_api.auth import require_operator
from voice_api.config import get_settings
from voice_api.db import get_session
from voice_api.integrations.vault import CredentialVault, VaultError
from voice_api.integrations.whatsapp import InboundWindow, WhatsAppAdapter, verify_signature
from voice_api.models import (
    IntegrationConnection,
    IntegrationMedia,
    IntegrationSecret,
    ToolInvocation,
)
from voice_api.models.common import new_id

router = APIRouter(prefix="/api/integrations", tags=["integrations"])
_inbound_window = InboundWindow()
Session = Depends(get_session)
Operator = Depends(require_operator)


class ConnectionBody(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    provider: str = Field(pattern="^whatsapp$")
    config: dict = Field(default_factory=dict)
    enabled: bool = False


class SecretBody(BaseModel):
    value: str = Field(min_length=1, max_length=8192)


class MediaImportBody(BaseModel):
    provider_media_id: str = Field(min_length=1, max_length=120)
    filename: str = Field(min_length=1, max_length=255)
    mime_type: str = Field(min_length=1, max_length=100)
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern="^[a-f0-9]{64}$")


def summary(connection: IntegrationConnection, *, secret_names: list[str]) -> dict:
    return {
        "id": connection.id,
        "label": connection.label,
        "provider": connection.provider,
        "config": connection.config,
        "enabled": connection.enabled,
        "secret_names": secret_names,
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


@router.get("")
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


@router.post("", status_code=201)
async def create_connection(
    body: ConnectionBody,
    session: AsyncSession = Session,
    _: None = Operator,
) -> dict:
    row = IntegrationConnection(id=new_id(), **body.model_dump())
    session.add(row)
    await session.commit()
    return summary(row, secret_names=[])


@router.put("/{connection_id}/secrets/{name}", status_code=204)
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


@router.post("/{connection_id}/rotate-secrets", status_code=204)
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


@router.get("/{connection_id}/media")
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


@router.post("/{connection_id}/media/import", status_code=201)
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


@router.post("/{connection_id}/media/upload", status_code=201)
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


@router.get("/{connection_id}/templates")
async def templates(
    connection_id: str,
    session: AsyncSession = Session,
    _: None = Operator,
) -> dict:
    connection = await connection_or_404(session, connection_id)
    adapter = await whatsapp(session, connection)
    async with adapter:
        return {"templates": await adapter.template_catalog()}


@router.get("/whatsapp/{connection_id}/webhook")
async def verify_webhook(
    connection_id: str,
    request: Request,
    session: AsyncSession = Session,
) -> str:
    await connection_or_404(session, connection_id)
    verify = await secret_value(session, connection_id, "verify_token")
    if request.query_params.get("hub.verify_token") != verify:
        raise HTTPException(403, "Webhook verification failed")
    return request.query_params.get("hub.challenge", "")


@router.post("/whatsapp/{connection_id}/webhook", status_code=204)
async def receive_webhook(
    connection_id: str, request: Request, session: AsyncSession = Session
) -> None:
    await connection_or_404(session, connection_id)
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    app_secret = await secret_value(session, connection_id, "app_secret")
    if not verify_signature(body, signature, app_secret):
        raise HTTPException(403, "Webhook signature failed")
    payload = await request.json()
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for message in value.get("messages", []):
                _inbound_window.observe(
                    connection_id, message.get("from"), message.get("timestamp")
                )
            for status in value.get("statuses", []):
                message_id = status.get("id")
                if not isinstance(message_id, str):
                    continue
                invocation = await session.scalar(
                    select(ToolInvocation).where(ToolInvocation.provider_message_id == message_id)
                )
                if invocation is not None:
                    receipt = {key: value for key, value in status.items() if key != "conversation"}
                    if receipt not in invocation.receipts:
                        invocation.receipts = [*invocation.receipts, receipt]
    await session.commit()
