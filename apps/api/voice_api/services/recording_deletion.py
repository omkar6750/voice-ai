"""Exact-set confirmation and manual, resumable deletion; no scheduled work."""

import asyncio
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from voice_api.core.config import get_settings
from voice_api.models import Call, Run
from voice_api.models.artifacts import RecordingDeletion, RecordingDeletionItem, RunArtifact
from voice_api.schemas.recordings import RecordingDeletionSelection
from voice_api.services.artifact_service import artifact_path
from voice_api.services.recording_storage import get_recording_storage

TERMINAL_RUNS = {"completed", "failed", "cancelled", "incomplete"}
RECORDING_KINDS = {"input", "output", "mixed"}


async def assert_runs_recordings_deletable(session: AsyncSession, run_ids: list[str]) -> None:
    """Call BEFORE deleting runs or disabling FK triggers; caller supplies scoped DB IDs.

    Lock parent runs so concurrent registration cannot pass the guard during deletion.
    Keep these locks in the SAME transaction as the hard delete. Do not commit between.
    """
    if not run_ids:
        return
    await session.scalars(
        select(Run.id).where(Run.id.in_(run_ids)).order_by(Run.id).with_for_update()
    )
    present = await session.scalar(
        select(RunArtifact.id)
        .where(
            RunArtifact.run_id.in_(run_ids),
            RunArtifact.storage_backend.in_(["cloudinary", "supabase"]),
            RunArtifact.deleted_at.is_(None),
        )
        .limit(1)
    )
    if present:
        raise HTTPException(409, "Delete run recordings manually before deleting their owning data")


def fingerprint(row: RunArtifact) -> dict:
    return {
        "id": row.id,
        "run_id": row.run_id,
        "sha256": row.sha256,
        "size_bytes": row.size_bytes,
        "storage_backend": row.storage_backend,
        "public_id": row.vendor_public_id,
        "asset_id": row.vendor_asset_id,
        "path": row.path,
    }


def eligible(row: RunArtifact, run_status: str) -> bool:
    return (
        run_status in TERMINAL_RUNS
        and row.storage_status != "uploading"
        and row.deleted_at is None
        and row.deletion_requested_at is None
    )


def confirmation_text(operation: RecordingDeletion) -> str:
    if operation.scope == "all_current_org":
        return f"DELETE ALL RECORDINGS {operation.org_id}"
    return f"DELETE {len(operation.snapshot)} RECORDINGS"


async def preview(session: AsyncSession, actor: str, selection: RecordingDeletionSelection) -> dict:
    query = (
        select(RunArtifact, Run.status)
        .join(Run, Run.id == RunArtifact.run_id)
        .where(RunArtifact.kind.in_(RECORDING_KINDS))
    )
    if selection.scope == "artifacts":
        query = query.where(RunArtifact.id.in_(selection.ids))
    elif selection.scope == "runs":
        query = query.where(Run.id.in_(selection.ids))
    elif selection.scope == "calls":
        query = query.join(Call, Call.run_id == Run.id).where(Call.id.in_(selection.ids))
    elif selection.scope == "utc_range":
        query = query.where(Run.created_at >= selection.start, Run.created_at < selection.end)
    rows = (await session.execute(query.order_by(RunArtifact.id))).all()
    selected = [row for row, status in rows if eligible(row, status)]
    token = secrets.token_urlsafe(32)
    operation = RecordingDeletion(
        actor_id=actor,
        confirmation_hash=hashlib.sha256(token.encode()).hexdigest(),
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        scope=selection.scope,
        snapshot=[fingerprint(row) for row in selected],
        status="preview",
    )
    session.add(operation)
    await session.commit()
    return {
        "operation_id": operation.id,
        "confirmation_token": token,
        "expires_at": operation.expires_at,
        "artifact_ids": [row.id for row in selected],
        "size_bytes": sum(row.size_bytes or 0 for row in selected),
        "excluded": len(rows) - len(selected),
        "confirmation_text": confirmation_text(operation),
    }


async def owned_operation(
    session: AsyncSession, operation_id: str, actor: str
) -> RecordingDeletion:
    operation = await session.get(
        RecordingDeletion, operation_id, with_for_update=True, populate_existing=True
    )
    if operation is None or operation.actor_id != actor:
        raise HTTPException(404, "Deletion operation not found")
    return operation


async def execute(session: AsyncSession, operation_id: str, actor: str, token: str, text: str):
    operation = await owned_operation(session, operation_id, actor)
    if not secrets.compare_digest(
        operation.confirmation_hash, hashlib.sha256(token.encode()).hexdigest()
    ):
        raise HTTPException(403, "Invalid recording confirmation")
    if text != confirmation_text(operation):
        raise HTTPException(422, "Confirmation text does not match")
    if operation.status != "preview":
        return operation  # Execution replay never starts another deletion batch.
    if operation.expires_at <= datetime.now(UTC):
        raise HTTPException(410, "Recording confirmation expired")
    ids = [item["id"] for item in operation.snapshot]
    rows = (
        await session.execute(
            select(RunArtifact, Run.status)
            .join(Run, Run.id == RunArtifact.run_id)
            .where(RunArtifact.id.in_(ids))
            .order_by(RunArtifact.id)
            .with_for_update(of=RunArtifact)
            .execution_options(populate_existing=True)
        )
    ).all()
    expected = {item["id"]: item for item in operation.snapshot}
    if len(rows) != len(ids) or any(
        not eligible(row, status) or fingerprint(row) != expected[row.id] for row, status in rows
    ):
        raise HTTPException(409, "Recording snapshot changed; preview again")
    now = datetime.now(UTC)
    for row, _ in rows:
        row.deletion_requested_at = now
        row.storage_status = "deleting"
        session.add(
            RecordingDeletionItem(operation_id=operation.id, artifact_id=row.id, status="pending")
        )
    operation.status = "pending" if rows else "completed"
    operation.started_at = now
    # Commit the access block and every work item before any external deletion.
    await session.commit()
    return operation


async def continue_deletion(session: AsyncSession, operation_id: str, actor: str):
    operation = await owned_operation(session, operation_id, actor)
    if operation.status == "preview":
        raise HTTPException(409, "Confirm deletion first")
    if operation.status == "completed":
        return
    pairs = (
        await session.execute(
            select(RecordingDeletionItem, RunArtifact)
            .join(RunArtifact, RunArtifact.id == RecordingDeletionItem.artifact_id)
            .where(
                RecordingDeletionItem.operation_id == operation.id,
                RecordingDeletionItem.status.in_(["pending", "failed"]),
            )
            .order_by(RecordingDeletionItem.id)
            .limit(100)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).all()
    missing = set()
    for _, row in pairs:
        if row.storage_backend == "cloudinary" and not row.vendor_asset_id:
            try:
                stored = await get_recording_storage().resolve(
                    row.vendor_public_id, row.sha256, row.size_bytes
                )
                if stored is None:
                    missing.add(row.id)
                else:
                    row.vendor_asset_id, row.vendor_version, row.vendor_format = (
                        stored.asset_id,
                        stored.version,
                        stored.format,
                    )
            except Exception:
                pass  # Uncertain identity remains blocked and manually retryable.
    await session.flush()
    cloud = [
        row.vendor_asset_id
        for _, row in pairs
        if row.storage_backend == "cloudinary" and row.vendor_asset_id
    ]
    results = {}
    if cloud:
        try:
            results = await get_recording_storage().delete(cloud)
        except Exception:
            # Keep pending durable access blocks; error details must never reveal credentials.
            results = {}
    for item, row in pairs:
        try:
            if (
                row.storage_backend == "cloudinary"
                and row.id not in missing
                and not results.get(row.vendor_asset_id, False)
            ):
                raise ValueError("Cloud deletion unconfirmed")
            if not Path(row.path).parts or Path(row.path).parts[0] != row.run_id:
                raise ValueError("Unsafe legacy path")
            local = artifact_path(Path(get_settings().recordings_dir), row.path)
            await asyncio.to_thread(local.unlink, missing_ok=True)
            row.deleted_at = datetime.now(UTC)
            row.storage_status = "deleted"
            row.deletion_error = item.error = None
            item.status = "deleted"
        except (OSError, ValueError):
            row.deletion_error = item.error = "Deletion unconfirmed; manually retry"
            item.status = "failed"
    await session.flush()
    items = (
        await session.scalars(
            select(RecordingDeletionItem).where(RecordingDeletionItem.operation_id == operation.id)
        )
    ).all()
    operation.status = (
        "completed"
        if all(item.status == "deleted" for item in items)
        else "failed"
        if any(item.status == "failed" for item in items)
        else "pending"
    )
    await session.commit()


async def progress(session: AsyncSession, operation: RecordingDeletion) -> dict:
    items = (
        await session.scalars(
            select(RecordingDeletionItem)
            .where(RecordingDeletionItem.operation_id == operation.id)
            .order_by(RecordingDeletionItem.id)
        )
    ).all()
    return {
        "id": operation.id,
        "status": operation.status,
        "total": len(operation.snapshot),
        "deleted": sum(item.status == "deleted" for item in items),
        "failed": sum(item.status == "failed" for item in items),
        "pending": sum(item.status == "pending" for item in items),
        "items": [
            {"artifact_id": item.artifact_id, "status": item.status, "error": item.error}
            for item in items
        ],
    }
