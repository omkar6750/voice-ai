"""API assigns artifact identities; runtime uploads directly using scoped grants."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from voice_api.api.deps import get_session
from voice_api.api.v1.endpoints.runtime import authenticate, authorize
from voice_api.core.runtime_config import get_runtime_settings as get_settings
from voice_api.models import RunArtifact
from voice_api.models.common import now
from voice_api.services.artifact_service import artifact_path, file_metadata
from voice_api.services.private_storage import (
    MAX_PRIVATE_BYTES,
    get_private_storage,
    object_identity,
)
from voice_api.services.recording_storage import get_recording_storage, recording_identity
from voice_shared.contracts import ArtifactRequest
from voice_shared.logging import redact

router = APIRouter(
    prefix="/runtime/artifacts", tags=["runtime-artifacts"], dependencies=[Depends(authenticate)]
)
Session = Depends(get_session)


async def artifact(session, body):
    _, run = await authorize(session, body, cleanup=True)
    settings = get_settings()
    if body.kind == "pipeline_log" and not run.resolved_config.get("_resolved", {}).get(
        "pipeline_logs_enabled"
    ):
        raise HTTPException(409, "Pipeline logging disabled")
    maximum = (
        MAX_PRIVATE_BYTES
        if body.kind in {"pipeline_log", "runtime_log"}
        else settings.recording_max_bytes
    )
    if body.size_bytes > maximum:
        raise HTTPException(413, "Artifact exceeds size limit")
    row = await session.get(RunArtifact, str(body.artifact_id), with_for_update=True)
    if row:
        if (
            (row.run_id, row.kind, row.size_bytes, row.sha256)
            != (run.id, body.kind, body.size_bytes, body.sha256)
            or row.deleted_at
            or row.deletion_requested_at
        ):
            raise HTTPException(409, "Artifact identity conflict")
        return row
    local = settings.env.casefold() in {"dev", "development", "local"}
    filename = (
        f"{body.kind.removesuffix('_log')}.log"
        if body.kind in {"pipeline_log", "runtime_log"}
        else f"{body.kind}.wav"
    )
    backend = (
        "local"
        if local
        else ("supabase" if body.kind in {"pipeline_log", "runtime_log"} else "cloudinary")
    )
    public_id = (
        recording_identity(run.org_id, run.id, str(body.artifact_id))
        if backend == "cloudinary"
        else object_identity(run.org_id, str(body.artifact_id), "diagnostics", body.sha256)
        if backend == "supabase"
        else None
    )
    row = RunArtifact(
        id=str(body.artifact_id),
        org_id=run.org_id,
        run_id=run.id,
        kind=body.kind,
        path=f"{run.id}/{filename}",
        sha256=body.sha256,
        size_bytes=body.size_bytes,
        duration_seconds=body.duration_seconds,
        sample_rate=body.sample_rate,
        channels=body.channels,
        sample_width=body.sample_width,
        storage_backend=backend,
        storage_status="uploading",
        vendor_public_id=public_id,
        expires_at=now()
        + timedelta(
            days=run.resolved_config.get("_resolved", {}).get(
                "pipeline_log_retention_days"
                if body.kind in {"pipeline_log", "runtime_log"}
                else "recording_retention_days",
                7,
            )
        ),
    )
    session.add(row)
    await session.commit()
    return row


@router.post("/grant")
async def grant(body: ArtifactRequest, session=Session):
    row = await artifact(session, body)
    if row.storage_status == "available":
        return {"available": True, "provider": row.storage_backend}
    if row.storage_backend == "local":
        return {
            "provider": "local",
            "upload_url": f"/api/v1/runtime/artifacts/{row.run_id}/{row.id}/upload",
        }
    if row.storage_backend == "cloudinary":
        import cloudinary.utils

        settings = get_settings()
        storage = get_recording_storage()
        fields = {
            "timestamp": str(int(time.time())),
            "public_id": row.vendor_public_id,
            "type": "authenticated",
            "overwrite": "false",
            "unique_filename": "false",
            "context": f"sha256={row.sha256}",
        }
        fields["signature"] = cloudinary.utils.api_sign_request(
            fields, settings.cloudinary_api_secret.get_secret_value()
        )
        fields["api_key"] = settings.cloudinary_api_key.get_secret_value()
        return {
            "provider": "cloudinary",
            "upload_url": f"https://api.cloudinary.com/v1_1/{storage.options['cloud_name']}/video/upload",
            "fields": fields,
        }
    storage = get_private_storage()
    async with httpx.AsyncClient(timeout=15) as client:
        await storage._private_bucket(client)
        response = await client.post(
            f"{storage.base}/object/upload/sign/{storage.bucket}/{row.vendor_public_id}",
            headers=storage.headers,
            json={},
        )
        response.raise_for_status()
        url = response.json()["url"]
    # Provider returns a relative storage path; never accept another upload origin.
    from urllib.parse import urljoin, urlsplit

    url = urljoin(storage.base + "/", url.lstrip("/")) if not url.startswith("https://") else url
    if urlsplit(url).netloc != urlsplit(storage.base).netloc:
        raise HTTPException(502, "Invalid storage upload grant")
    return {"provider": "supabase", "upload_url": url}


@router.put("/{run_id}/{artifact_id}/upload")
async def upload(run_id: str, artifact_id: str, request: Request, session=Session):
    from voice_api.db.tenant_scope import bind_run_organization

    await bind_run_organization(session, run_id)
    row = await session.get(RunArtifact, artifact_id, with_for_update=True)
    if row is None or row.run_id != run_id or row.storage_backend != "local":
        raise HTTPException(404, "Local upload unavailable")
    body = SimpleNamespace(
        run_id=row.run_id,
        generation=request.headers.get("X-Voice-Generation"),
        boot_id=request.headers.get("X-Voice-Boot"),
        grant=SimpleNamespace(
            get_secret_value=lambda: request.headers.get("X-Voice-Session-Grant", "")
        ),
    )
    await authorize(session, body, cleanup=True)
    path = artifact_path(Path(get_settings().recordings_dir), row.path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".upload")
    digest = hashlib.sha256()
    size = 0
    f = await asyncio.to_thread(temp.open, "wb")
    try:
        async for chunk in request.stream():
            size += len(chunk)
            if size > row.size_bytes:
                raise HTTPException(413, "Upload exceeds expected size")
            digest.update(chunk)
            await asyncio.to_thread(f.write, chunk)
        await asyncio.to_thread(f.flush)
        import os

        await asyncio.to_thread(os.fsync, f.fileno())
    finally:
        await asyncio.to_thread(f.close)
    if size != row.size_bytes or digest.hexdigest() != row.sha256:
        raise HTTPException(422, "Upload checksum mismatch")
    await asyncio.to_thread(temp.replace, path)
    return {"uploaded": True}


@router.post("/complete")
async def complete(body: ArtifactRequest, session=Session):
    row = await artifact(session, body)
    if row.storage_status == "available":
        return {"id": row.id, "status": "available"}
    if row.storage_backend == "cloudinary":
        stored = await get_recording_storage().resolve(
            row.vendor_public_id, row.sha256, row.size_bytes
        )
        if stored is None:
            raise HTTPException(409, "Assigned recording not uploaded")
        row.vendor_asset_id = stored.asset_id
        row.vendor_version = stored.version
        row.vendor_format = stored.format
    elif row.storage_backend == "supabase":
        data = await get_private_storage().read(row.vendor_public_id)
        if len(data) != row.size_bytes or hashlib.sha256(data).hexdigest() != row.sha256:
            raise HTTPException(409, "Uploaded diagnostic size mismatch")
        for line in data.decode("utf-8").splitlines():
            value = json.loads(line)
            if value != redact(value):
                raise HTTPException(422, "Diagnostic upload contains private fields")
    else:
        path = artifact_path(Path(get_settings().recordings_dir), row.path)
        metadata = await asyncio.to_thread(
            file_metadata, path, row.kind not in {"pipeline_log", "runtime_log"}
        )
        if metadata["size_bytes"] != row.size_bytes or metadata["sha256"] != row.sha256:
            raise HTTPException(409, "Uploaded artifact integrity mismatch")
        if row.kind in {"pipeline_log", "runtime_log"}:
            data = await asyncio.to_thread(path.read_text, encoding="utf-8")
            for line in data.splitlines():
                value = json.loads(line)
                if value != redact(value):
                    raise HTTPException(422, "Diagnostic upload contains private fields")
        for field in ("duration_seconds", "sample_rate", "channels", "sample_width"):
            if field in metadata:
                setattr(row, field, metadata[field])
    row.storage_status = "available"
    row.storage_error = None
    await session.commit()
    return {"id": row.id, "status": "available"}
