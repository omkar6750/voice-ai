"""In-process runtime persistence; no HTTP request or service credential needed."""

import asyncio
from pathlib import Path
from time import perf_counter
from uuid import NAMESPACE_URL, uuid5

from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from voice_runtime.contracts.evidence import EvidenceBatch
from voice_runtime.execution.evidence_client import EvidenceDeliveryError
from voice_runtime.perf_diagnostics import is_enabled, timing

from voice_api.db.session import SessionFactory
from voice_api.db.tenant_scope import bind_run_organization


class LocalEvidenceIngestor:
    def __init__(self, run_id: str, *, org_id: str | None = None):
        self.run_id = run_id
        self.org_id = org_id

    async def ingest(self, records: list[dict]) -> None:
        # Acknowledgement follows the same validation, redaction and commit
        # boundary as the worker-facing API.
        from voice_api.api.v1.endpoints.evidence import ingest

        batch = EvidenceBatch(records=records)
        if any(record.run_id != self.run_id for record in batch.records):
            raise ValueError("Spool contains a different run")
        started = perf_counter() if is_enabled() else 0
        try:
            async with SessionFactory() as session:
                await bind_run_organization(session, self.run_id, expected_org_id=self.org_id)
                result = await ingest(self.run_id, batch, session, None)
            if result["accepted"] != len(records):
                raise ValueError("Incomplete acknowledgement")
        except HTTPException as exc:
            raise EvidenceDeliveryError(
                retryable=exc.status_code == 429 or exc.status_code >= 500
            ) from None
        except SQLAlchemyError:
            raise EvidenceDeliveryError(retryable=True) from None
        finally:
            if started:
                timing("evidence", "batch", (perf_counter() - started) * 1000, count=len(records))


async def register_local_artifacts(
    run_id: str, directory: Path, *, strict: bool = False, org_id: str | None = None
) -> list[str]:
    from voice_api.api.v1.endpoints.artifacts import ArtifactBody, register

    if not await asyncio.to_thread(directory.exists):
        return []
    failed_kinds: list[str] = []
    for kind in ("input", "output", "mixed", "pipeline_log"):
        filename = "pipeline.log" if kind == "pipeline_log" else f"{kind}.wav"
        if not await asyncio.to_thread((directory / filename).is_file):
            continue
        try:
            async with SessionFactory() as session:
                await bind_run_organization(session, run_id, expected_org_id=org_id)
                await register(
                    run_id,
                    ArtifactBody(
                        id=str(uuid5(NAMESPACE_URL, f"{run_id}/{kind}")),
                        kind=kind,
                        path=f"{run_id}/{filename}",
                    ),
                    session,
                )
        except Exception:
            failed_kinds.append(kind)
    if strict and failed_kinds:
        raise RuntimeError("Run artifacts could not be registered")
    return failed_kinds


async def local_claim(run_id: str, body: dict) -> dict:
    from voice_api.api.v1.endpoints.execution import claim
    from voice_api.schemas.execution import Claim

    async with SessionFactory() as session:
        await bind_run_organization(session, run_id)
        return await claim(run_id, Claim.model_validate(body), session)


async def local_progress(run_id: str, body: dict) -> dict:
    from voice_api.api.v1.endpoints.execution import progress
    from voice_api.schemas.execution import Progress

    async with SessionFactory() as session:
        await bind_run_organization(session, run_id)
        return await progress(run_id, Progress.model_validate(body), session)


async def local_callback(name: str, run_id: str, payload: dict) -> dict:
    from voice_api.api.v1.endpoints.calendar import (
        AvailabilityRequest,
        BookRequest,
        availability,
        book,
    )

    payload = {**payload, "run_id": run_id}
    async with SessionFactory() as session:
        await bind_run_organization(session, run_id)
        try:
            if name == "check_callback_availability":
                return await availability(
                    AvailabilityRequest.model_validate(payload), session, None
                )
            if name == "book_callback":
                return await book(BookRequest.model_validate(payload), session, None)
        except HTTPException as exc:
            if 400 <= exc.status_code < 500:
                return {"status": "error", "error": str(exc.detail)}
            raise
    raise ValueError("Unsupported local callback operation")
