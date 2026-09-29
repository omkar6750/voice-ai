"""Register completed artifacts and expire only explicitly recorded call files."""

import asyncio
import hashlib
import wave
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from voice_api.api.deps import get_session, require_legacy_owner, require_runtime_service
from voice_api.api.v1.endpoints.recordings import require_recording_access
from voice_api.core.config import get_settings
from voice_api.core.security import allow_organization_member
from voice_api.db.tenant_scope import bind_run_organization
from voice_api.models import Run
from voice_api.models.artifacts import RunArtifact
from voice_api.schemas.recordings import RecordingListResponse, RecordingResponse
from voice_api.services.artifact_service import artifact_path, file_metadata
from voice_api.services.private_storage import (
    MAX_PRIVATE_BYTES,
    check_identity,
    get_private_storage,
    object_identity,
    sanitized_diagnostics,
)
from voice_api.services.recording_storage import get_recording_storage, recording_identity
from voice_runtime.contracts.base import ConfigModel

router = APIRouter(tags=["artifacts"])
Session = Depends(get_session)


def hosted_log_bytes(path: Path) -> bytes:
    with path.open("rb") as stream:
        raw = stream.read(MAX_PRIVATE_BYTES + 1)
    return sanitized_diagnostics(raw)


class ArtifactBody(ConfigModel):
    id: str = Field(min_length=1, max_length=36)
    kind: Literal["input", "output", "mixed", "pipeline_log"]
    path: str


@router.post(
    "/runs/{run_id}/artifacts", status_code=201, dependencies=[Depends(require_runtime_service)]
)
async def register(run_id: str, body: ArtifactBody, session: AsyncSession = Session) -> dict:
    await bind_run_organization(session, run_id)
    run = await session.get(Run, run_id, with_for_update=True)
    if run is None:
        raise HTTPException(404, "Run not found")
    existing = await session.get(RunArtifact, body.id, with_for_update=True, populate_existing=True)
    if existing:
        if (existing.run_id, existing.kind, existing.path) != (run_id, body.kind, body.path):
            raise HTTPException(409, "Artifact identity conflict")
        if existing.deleted_at or existing.deletion_requested_at:
            return {"id": existing.id, "deleted_at": existing.deleted_at}
        if existing.storage_status == "available":
            return {"id": existing.id, "deleted_at": existing.deleted_at}
    resolved = run.resolved_config.get("_resolved", {})
    settings = get_settings()
    private_log = body.kind == "pipeline_log" and (
        settings.env != "dev" or bool(settings.supabase_url)
    )
    log_data = None
    if body.kind == "pipeline_log" and not resolved.get("pipeline_logs_enabled", False):
        raise HTTPException(409, "Pipeline logging disabled for this run")
    try:
        path = artifact_path(Path(get_settings().recordings_dir), body.path)
        filename = "pipeline.log" if body.kind == "pipeline_log" else f"{body.kind}.wav"
        if body.path != f"{run_id}/{filename}":
            raise ValueError("Artifact must belong to run directory")
        if private_log:
            log_data = await asyncio.to_thread(hosted_log_bytes, path)
            metadata = {"sha256": hashlib.sha256(log_data).hexdigest(), "size_bytes": len(log_data)}
        else:
            metadata = await asyncio.to_thread(file_metadata, path, body.kind != "pipeline_log")
    except (OSError, ValueError, EOFError, wave.Error):
        raise HTTPException(422, "Artifact missing, unsafe or invalid") from None
    if not existing and await session.scalar(
        select(RunArtifact.id).where(RunArtifact.path == body.path)
    ):
        raise HTTPException(409, "Artifact path already registered")
    retention = (
        "pipeline_log_retention_days" if body.kind == "pipeline_log" else "recording_retention_days"
    )
    row = existing or RunArtifact(
        id=body.id,
        run_id=run_id,
        kind=body.kind,
        path=body.path,
        expires_at=(
            datetime.now(UTC) + timedelta(days=resolved.get(retention, 7))
            if body.kind == "pipeline_log"
            else None
        ),
        **metadata,
    )
    if existing and (row.sha256 != metadata["sha256"] or row.size_bytes != metadata["size_bytes"]):
        raise HTTPException(409, "Finalized artifact changed")
    if private_log:
        row.storage_backend = "supabase"
        row.storage_status = "uploading"
        row.vendor_public_id = object_identity(run.org_id, row.id, "diagnostics", row.sha256)
    elif body.kind != "pipeline_log":
        row.storage_backend = "cloudinary"
        row.storage_status = "uploading"
        row.vendor_public_id = recording_identity(run.org_id, run_id, body.id)
    session.add(row)
    await session.commit()
    if private_log or body.kind != "pipeline_log":
        # Row lock serializes registration retries, deletion and serving. Persistent uploading
        # state survives process loss; replay verifies the same remote object before exposing it.
        row = await session.get(RunArtifact, body.id, with_for_update=True, populate_existing=True)
        if row.deleted_at or row.deletion_requested_at:
            return {"id": row.id, "deleted_at": row.deleted_at}
        try:
            if private_log:
                check_identity(row.vendor_public_id, row.org_id, row.id, "diagnostics")
                await get_private_storage().upload(row.vendor_public_id, log_data)
            else:
                stored = await get_recording_storage().upload(
                    path, row.vendor_public_id, row.sha256, row.size_bytes
                )
                row.vendor_asset_id, row.vendor_version, row.vendor_format = (
                    stored.asset_id,
                    stored.version,
                    stored.format,
                )
            row.storage_status, row.storage_error = "available", None
        except Exception:
            row.storage_status, row.storage_error = (
                "failed",
                "Artifact upload unconfirmed; replay registration to retry",
            )
            await session.commit()
            raise HTTPException(503, "Artifact upload unconfirmed") from None
        await session.commit()
    return {"id": row.id, "expires_at": row.expires_at}


@router.get(
    "/runs/{run_id}/artifacts",
    dependencies=[Depends(require_recording_access)],
    response_model=RecordingListResponse,
)
@allow_organization_member
async def list_artifacts(run_id: str, session: AsyncSession = Session) -> dict:
    rows = (
        await session.scalars(
            select(RunArtifact).where(RunArtifact.run_id == run_id).order_by(RunArtifact.created_at)
        )
    ).all()
    return {
        "artifacts": [RecordingResponse.model_validate(row) for row in rows],
        "total": len(rows),
    }


@router.get("/artifacts/{artifact_id}/file", dependencies=[Depends(require_recording_access)])
@allow_organization_member
async def download(artifact_id: str, session: AsyncSession = Session):
    row = await session.get(RunArtifact, artifact_id, with_for_update=True, populate_existing=True)
    if row is None:
        raise HTTPException(404, "Artifact not found")
    if (
        row.deleted_at
        or row.deletion_requested_at
        or (row.expires_at and row.expires_at <= datetime.now(UTC))
    ):
        raise HTTPException(410, "Artifact expired or deleted")
    if row.storage_backend in {"cloudinary", "supabase"}:
        if row.storage_status != "available":
            raise HTTPException(409, "Recording upload is not available")
        try:
            if row.storage_backend == "supabase":
                check_identity(row.vendor_public_id, row.org_id, row.id, "diagnostics")
                data = await get_private_storage().read(row.vendor_public_id)
            else:
                if row.vendor_public_id != recording_identity(row.org_id, row.run_id, row.id):
                    raise ValueError("Recording identity mismatch")
                data = await get_recording_storage().read(row.vendor_public_id, row.vendor_format)

            if len(data) != row.size_bytes or hashlib.sha256(data).hexdigest() != row.sha256:
                raise ValueError("Recording integrity mismatch")
        except Exception:
            raise HTTPException(503, "Recording unavailable") from None
        return Response(
            data,
            media_type="application/x-ndjson" if row.kind == "pipeline_log" else "audio/wav",
            headers={
                "Cache-Control": "no-store",
                "Content-Disposition": 'inline; filename="pipeline.jsonl"'
                if row.kind == "pipeline_log"
                else f'inline; filename="{row.kind}.wav"',
            },
        )
    try:
        path = artifact_path(Path(get_settings().recordings_dir), row.path)
        if not path.is_file():
            raise ValueError("Missing")
    except (ValueError, OSError):
        raise HTTPException(410, "Artifact unavailable") from None
    return FileResponse(path, filename=path.name, headers={"Cache-Control": "no-store"})


@router.post("/artifacts/expire", dependencies=[Depends(require_legacy_owner)])
async def expire(session: AsyncSession = Session) -> dict:
    now = datetime.now(UTC)
    rows = (
        await session.scalars(
            select(RunArtifact)
            .where(RunArtifact.expires_at <= now, RunArtifact.deleted_at.is_(None))
            .where(
                RunArtifact.storage_backend == "local", RunArtifact.deletion_requested_at.is_(None)
            )
            .order_by(RunArtifact.expires_at)
            .limit(100)
            .with_for_update(skip_locked=True)
        )
    ).all()
    deleted, failed = 0, 0
    for row in rows:
        try:
            if not Path(row.path).parts or Path(row.path).parts[0] != row.run_id:
                raise ValueError("Legacy path requires explicit migration before deletion")
            path = artifact_path(Path(get_settings().recordings_dir), row.path)
            await asyncio.to_thread(path.unlink, missing_ok=True)
            row.deleted_at, row.deletion_error = now, None
            deleted += 1
        except (OSError, ValueError):
            row.deletion_error = "File deletion failed; verify storage path and permissions"
            failed += 1
    await session.commit()
    return {"deleted": deleted, "failed": failed}
