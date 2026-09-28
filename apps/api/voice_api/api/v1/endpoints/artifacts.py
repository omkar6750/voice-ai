"""Register completed artifacts and expire only explicitly recorded call files."""

import asyncio
import wave
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from voice_api.api.deps import get_session, require_legacy_owner, require_runtime_service
from voice_api.core.config import get_settings
from voice_api.models import Run
from voice_api.models.artifacts import RunArtifact
from voice_api.services.artifact_service import artifact_path, file_metadata
from voice_runtime.contracts.base import ConfigModel

router = APIRouter(tags=["artifacts"])
Session = Depends(get_session)


class ArtifactBody(ConfigModel):
    id: str = Field(min_length=1, max_length=36)
    kind: Literal["input", "output", "mixed", "pipeline_log"]
    path: str


@router.post(
    "/runs/{run_id}/artifacts", status_code=201, dependencies=[Depends(require_runtime_service)]
)
async def register(run_id: str, body: ArtifactBody, session: AsyncSession = Session) -> dict:
    run = await session.get(Run, run_id, with_for_update=True)
    if run is None:
        raise HTTPException(404, "Run not found")
    existing = await session.get(RunArtifact, body.id)
    if existing:
        if (existing.run_id, existing.kind, existing.path) != (run_id, body.kind, body.path):
            raise HTTPException(409, "Artifact identity conflict")
        return {"id": existing.id, "deleted_at": existing.deleted_at}
    resolved = run.resolved_config.get("_resolved", {})
    if body.kind == "pipeline_log" and not resolved.get("pipeline_logs_enabled", False):
        raise HTTPException(409, "Pipeline logging disabled for this run")
    try:
        path = artifact_path(Path(get_settings().recordings_dir), body.path)
        filename = "pipeline.log" if body.kind == "pipeline_log" else f"{body.kind}.wav"
        if body.path != f"{run_id}/{filename}":
            raise ValueError("Artifact must belong to run directory")
        metadata = await asyncio.to_thread(file_metadata, path, body.kind != "pipeline_log")
    except (OSError, ValueError, EOFError, wave.Error):
        raise HTTPException(422, "Artifact missing, unsafe or invalid") from None
    if await session.scalar(select(RunArtifact.id).where(RunArtifact.path == body.path)):
        raise HTTPException(409, "Artifact path already registered")
    retention = (
        "pipeline_log_retention_days" if body.kind == "pipeline_log" else "recording_retention_days"
    )
    row = RunArtifact(
        id=body.id,
        run_id=run_id,
        kind=body.kind,
        path=body.path,
        expires_at=datetime.now(UTC) + timedelta(days=resolved.get(retention, 7)),
        **metadata,
    )
    session.add(row)
    await session.commit()
    return {"id": row.id, "expires_at": row.expires_at}


@router.get("/runs/{run_id}/artifacts", dependencies=[Depends(require_legacy_owner)])
async def list_artifacts(run_id: str, session: AsyncSession = Session) -> dict:
    rows = (
        await session.scalars(
            select(RunArtifact).where(RunArtifact.run_id == run_id).order_by(RunArtifact.created_at)
        )
    ).all()
    return {
        "artifacts": [
            {
                "id": row.id,
                "kind": row.kind,
                "sha256": row.sha256,
                "size_bytes": row.size_bytes,
                "expires_at": row.expires_at,
                "deleted_at": row.deleted_at,
                "deletion_error": row.deletion_error,
            }
            for row in rows
        ]
    }


@router.get("/artifacts/{artifact_id}/file", dependencies=[Depends(require_legacy_owner)])
async def download(artifact_id: str, session: AsyncSession = Session):
    row = await session.get(RunArtifact, artifact_id)
    if row is None:
        raise HTTPException(404, "Artifact not found")
    if row.deleted_at or (row.expires_at and row.expires_at <= datetime.now(UTC)):
        raise HTTPException(410, "Artifact expired or deleted")
    try:
        path = artifact_path(Path(get_settings().recordings_dir), row.path)
        if not path.is_file():
            raise ValueError("Missing")
    except (ValueError, OSError):
        raise HTTPException(410, "Artifact unavailable") from None
    return FileResponse(path, filename=path.name)


@router.post("/artifacts/expire", dependencies=[Depends(require_legacy_owner)])
async def expire(session: AsyncSession = Session) -> dict:
    now = datetime.now(UTC)
    rows = (
        await session.scalars(
            select(RunArtifact)
            .where(RunArtifact.expires_at <= now, RunArtifact.deleted_at.is_(None))
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
