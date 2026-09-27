"""Canonical persistence for normalized run diagnostics."""

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from voice_api.models import RunDiagnostic
from voice_api.schemas.diagnostics import DiagnosticInput


def _fields(run_id: str, diagnostic: DiagnosticInput) -> dict:
    return {
        "run_id": run_id,
        "severity": diagnostic.severity,
        "category": diagnostic.category,
        "source": diagnostic.source,
        "code": diagnostic.code,
        "message": diagnostic.message,
        "detail": diagnostic.detail,
        "retryable": diagnostic.retryable,
        "uncertain": diagnostic.uncertain,
        "provider_request_id": diagnostic.provider_request_id,
        "http_status": diagnostic.http_status,
        "retry_after_seconds": diagnostic.retry_after_seconds,
        "metadata_json": diagnostic.metadata,
        "occurred_at": diagnostic.occurred_at,
    }


async def persist_diagnostic(
    session: AsyncSession, run_id: str, diagnostic: DiagnosticInput
) -> RunDiagnostic:
    fields = _fields(run_id, diagnostic)
    row = await session.get(RunDiagnostic, diagnostic.diagnostic_id)
    if row is not None:
        if any(getattr(row, key) != value for key, value in fields.items()):
            raise HTTPException(409, "Diagnostic identity conflicts with existing record")
        return row
    row = RunDiagnostic(id=diagnostic.diagnostic_id, **fields)
    session.add(row)
    await session.flush()
    return row


async def persist_diagnostics(
    session: AsyncSession, run_id: str, diagnostics: list[DiagnosticInput]
) -> None:
    for diagnostic in diagnostics:
        await persist_diagnostic(session, run_id, diagnostic)
