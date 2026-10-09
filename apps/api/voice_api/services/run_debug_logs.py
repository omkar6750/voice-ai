"""Retained log excerpts with run ownership, integrity and safe storage checks."""

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select
from voice_shared.logging import redact

from voice_api.core.config import get_settings
from voice_api.models.artifacts import RunArtifact
from voice_api.services.artifact_service import artifact_path
from voice_api.services.private_storage import (
    MAX_PRIVATE_BYTES,
    check_identity,
    get_private_storage,
)


async def inventory(session, run_id):
    rows = (
        await session.scalars(
            select(RunArtifact)
            .where(
                RunArtifact.run_id == run_id, RunArtifact.kind.in_(["pipeline_log", "runtime_log"])
            )
            .order_by(RunArtifact.created_at, RunArtifact.id)
        )
    ).all()
    return [
        {
            "id": row.id,
            "kind": row.kind,
            "state": "expired"
            if row.deleted_at
            or row.deletion_requested_at
            or (row.expires_at and row.expires_at <= datetime.now(UTC))
            else row.storage_status,
            "size_bytes": row.size_bytes,
        }
        for row in rows
    ]


async def excerpt(session, run_id, artifact_id, severity, operation_id, after, limit):
    row = await session.scalar(
        select(RunArtifact).where(
            RunArtifact.run_id == run_id,
            RunArtifact.id == artifact_id,
            RunArtifact.kind.in_(["pipeline_log", "runtime_log"]),
        )
    )
    if row is None:
        raise HTTPException(404, "Run log artifact not found")
    if (
        row.deleted_at
        or row.deletion_requested_at
        or (row.expires_at and row.expires_at <= datetime.now(UTC))
    ):
        raise HTTPException(410, "Run log artifact expired")
    if row.storage_status != "available":
        raise HTTPException(409, "Run log artifact not available")
    if row.size_bytes is None or row.size_bytes > MAX_PRIVATE_BYTES:
        raise HTTPException(409, "Run log artifact size unavailable or too large")
    try:
        if row.storage_backend == "supabase":
            check_identity(row.vendor_public_id, row.org_id, row.id, "diagnostics")
            raw = await get_private_storage().read(row.vendor_public_id)
        elif row.storage_backend == "local":
            path = artifact_path(Path(get_settings().recordings_dir), row.path)

            def read():
                with path.open("rb") as stream:
                    return stream.read(MAX_PRIVATE_BYTES + 1)

            raw = await asyncio.to_thread(read)
        else:
            raise ValueError("Unsupported log storage")
        if len(raw) != row.size_bytes or hashlib.sha256(raw).hexdigest() != row.sha256:
            raise ValueError("Integrity mismatch")
        lines = raw.decode("utf-8").splitlines()
    except (ValueError, OSError, UnicodeError):
        raise HTTPException(503, "Run log artifact unavailable") from None
    records, cursor, used = [], after, 0
    levels = {"ERROR", "CRITICAL"} if severity == "error" else {"WARNING", "ERROR", "CRITICAL"}
    while cursor < len(lines) and len(records) < limit:
        line = lines[cursor]
        cursor += 1
        try:
            value = json.loads(line)
            if not isinstance(value, dict):
                continue
            if value.get("run_id") and value["run_id"].replace("-", "") != run_id.replace("-", ""):
                continue
            if severity != "all" and value.get("level", "INFO").upper() not in levels:
                continue
            if operation_id and operation_id not in {
                value.get("operation_id"),
                value.get("span_id"),
                value.get("parent_span_id"),
            }:
                continue
            safe = redact(value)
            size = len(json.dumps(safe))
            if used + size > 32000:
                if not records:
                    records.append(
                        {
                            "line": cursor - 1,
                            "state": "oversized_record",
                            "total_chars": size,
                            "excerpt": json.dumps(safe)[:31000],
                        }
                    )
                    break
                cursor -= 1
                break
            records.append(safe)
            used += size
        except (ValueError, TypeError):
            continue
    return {
        "source": "retained_artifact",
        "artifact_id": row.id,
        "records": records,
        "next_offset": cursor if cursor < len(lines) else None,
    }
