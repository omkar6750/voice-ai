"""Member-readable execution overview and explicit evidence payload selection."""

from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field, JsonValue
from sqlalchemy import select
from voice_api.core.security import allow_organization_member, require_organization_access
from voice_api.db.session import get_session
from voice_api.models import RunDiagnostic
from voice_api.services import run_debug

router = APIRouter(
    prefix="/runs/{run_id}/debug",
    tags=["run-debug"],
    dependencies=[Depends(require_organization_access)],
)
Session = Depends(get_session)


class EvidenceSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: list[str] = Field(min_length=1, max_length=100)
    materialize_context: bool = False
    sections: list[Literal["input", "output", "error", "metrics", "context", "related_events"]] = [
        "input",
        "output",
        "error",
        "metrics",
    ]


@router.get("", response_model=dict[str, JsonValue])
@allow_organization_member
async def inspect_run(
    run_id: str,
    after: int = Query(0, ge=0),
    max_chars: int = Query(1_000_000, ge=1024, le=1_000_000),
    expected_hash: str | None = None,
    session=Session,
):
    return run_debug.bounded(
        await run_debug.inspect(session, run_id), after, max_chars, expected_hash
    )


@router.post("/operations", response_model=dict[str, JsonValue])
@allow_organization_member
async def inspect_operations(
    run_id: str,
    body: EvidenceSelection,
    after: int = Query(0, ge=0),
    max_chars: int = Query(32000, ge=1024, le=128000),
    expected_hash: str | None = None,
    session=Session,
):
    return run_debug.bounded(
        await run_debug.details(session, run_id, body.ids, body.sections, body.materialize_context),
        after,
        max_chars,
        expected_hash,
    )


@router.get("/config", response_model=dict[str, JsonValue])
@allow_organization_member
async def get_run_config(
    run_id: str,
    section: str | None = None,
    after: int = Query(0, ge=0),
    max_chars: int = Query(32000, ge=1024, le=128000),
    expected_hash: str | None = None,
    session=Session,
):
    run = await run_debug.require_run(session, run_id)
    from voice_api.core.security import safe_evidence
    from voice_runtime.execution.redaction import redact

    config = safe_evidence(redact(run.resolved_config))
    return run_debug.bounded(
        {
            "config_hash": run.config_hash,
            "config": config if section is None else config.get(section),
            "state": "recorded" if section is None or section in config else "not_recorded",
        },
        after,
        max_chars,
        expected_hash,
    )


@router.get("/logs", response_model=dict[str, JsonValue])
@allow_organization_member
async def read_run_logs(
    run_id: str,
    severity: Literal["all", "warning", "error"] = "warning",
    after: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    operation_id: str | None = None,
    artifact_id: str | None = None,
    session=Session,
):
    await run_debug.require_run(session, run_id)
    from voice_api.services import run_debug_logs

    if artifact_id:
        return await run_debug_logs.excerpt(
            session, run_id, artifact_id, severity, operation_id, after, limit
        )
    query = select(RunDiagnostic).where(RunDiagnostic.run_id == run_id)
    if severity != "all":
        query = query.where(
            RunDiagnostic.severity.in_(["warning", "error"] if severity == "warning" else ["error"])
        )
    if operation_id:
        query = query.where(
            (RunDiagnostic.metadata_json["operation_id"].astext == operation_id)
            | (RunDiagnostic.metadata_json["request_id"].astext == operation_id)
        )
    rows = (
        await session.scalars(
            query.order_by(RunDiagnostic.occurred_at, RunDiagnostic.id)
            .offset(after)
            .limit(limit + 1)
        )
    ).all()
    from fastapi.encoders import jsonable_encoder

    return jsonable_encoder(
        {
            "source": "persisted_diagnostics",
            "artifacts": await run_debug_logs.inventory(session, run_id),
            "records": [
                {
                    "id": d.id,
                    "at": d.occurred_at,
                    "severity": d.severity,
                    "message": d.message,
                    "code": d.code,
                    "detail_available": d.detail is not None,
                }
                for d in rows[:limit]
            ],
            "next_offset": after + limit if len(rows) > limit else None,
        }
    )
