"""Append derived evidence; preserve replay identity and captured history boundaries."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import AwareDatetime, Field, JsonValue, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from voice_runtime.contracts.base import ConfigModel

from voice_api.auth import require_operator
from voice_api.db import get_session
from voice_api.evidence_ingestion import verify_same
from voice_api.evidence_security import safe_evidence
from voice_api.models import (
    Classification,
    ContactFact,
    ContextSummary,
    ConversationMessage,
    Run,
    TraceSpan,
)

router = APIRouter(
    prefix="/api/runs/{run_id}/analysis",
    tags=["analysis"],
    dependencies=[Depends(require_operator)],
)
Session = Depends(get_session)
Id = Annotated[str, Field(min_length=1, max_length=36)]


class SourceEvidence(ConfigModel):
    id: Id
    source_message_ids: list[Id] = Field(min_length=1)
    occurred_at: AwareDatetime

    @model_validator(mode="after")
    def distinct_sources(self):
        if len(set(self.source_message_ids)) != len(self.source_message_ids):
            raise ValueError("Source message IDs must be distinct")
        return self


class ClassificationBody(SourceEvidence):
    kind: Literal["classification"]
    operation_id: Id
    status: Literal["completed", "failed"]
    verdict: Literal["hot", "warm", "cold"] | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    evidence: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def truthful_outcome(self):
        if (self.status == "completed") != (self.verdict is not None):
            raise ValueError(
                "Completed classification needs a verdict; failed classification cannot have one"
            )
        if self.status == "failed" and self.confidence is not None:
            raise ValueError("Failed classification cannot have confidence")
        return self


class SummaryBody(SourceEvidence):
    kind: Literal["summary"]
    operation_id: Id
    content: str = Field(min_length=1)


class FactBody(SourceEvidence):
    kind: Literal["fact"]
    name: str = Field(min_length=1, max_length=120)
    value: JsonValue
    supersedes_id: Id | None = None


AnalysisBody = Annotated[ClassificationBody | SummaryBody | FactBody, Field(discriminator="kind")]


@router.post("", status_code=201)
async def append(run_id: str, body: AnalysisBody, session: AsyncSession = Session) -> dict:
    run = await session.get(Run, run_id, with_for_update=True)
    if run is None:
        raise HTTPException(404, "Run not found")
    messages = (
        await session.scalars(
            select(ConversationMessage).where(
                ConversationMessage.id.in_(body.source_message_ids),
                ConversationMessage.run_id == run_id,
            )
        )
    ).all()
    if len(messages) != len(body.source_message_ids):
        raise HTTPException(422, "Analysis references missing or foreign source messages")
    values = safe_evidence(body.model_dump(exclude={"kind", "id"}))
    values["run_id"] = run_id
    model = {"classification": Classification, "summary": ContextSummary, "fact": ContactFact}[
        body.kind
    ]
    if isinstance(body, FactBody):
        if run.contact_id is None:
            raise HTTPException(422, "Contact facts require a contact-linked run")
        values["contact_id"] = run.contact_id
        if body.supersedes_id:
            previous = await session.get(ContactFact, body.supersedes_id)
            if (
                previous is None
                or previous.contact_id != run.contact_id
                or previous.name != body.name
                or previous.occurred_at > body.occurred_at
            ):
                raise HTTPException(422, "Invalid fact supersession")
    else:
        operation = await session.get(TraceSpan, body.operation_id)
        expected = (
            "failed"
            if isinstance(body, ClassificationBody) and body.status == "failed"
            else "completed"
        )
        if operation is None or operation.run_id != run_id or operation.status != expected:
            raise HTTPException(422, "Analysis needs a matching finalized operation")
    existing = await session.get(model, body.id)
    if existing:
        verify_same(existing, values)
        return {"id": existing.id}
    session.add(model(id=body.id, **values))
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(409, "Analysis conflicts with existing evidence") from None
    return {"id": body.id}


@router.get("")
async def history(run_id: str, session: AsyncSession = Session) -> dict:
    if await session.get(Run, run_id) is None:
        raise HTTPException(404, "Run not found")
    result = {}
    for key, model in (
        ("classifications", Classification),
        ("summaries", ContextSummary),
        ("facts", ContactFact),
    ):
        rows = (
            await session.scalars(
                select(model).where(model.run_id == run_id).order_by(model.occurred_at, model.id)
            )
        ).all()
        result[key] = [
            {column.name: getattr(row, column.name) for column in model.__table__.columns}
            for row in rows
        ]
    return result
