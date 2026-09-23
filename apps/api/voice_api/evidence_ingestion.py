"""Atomic, idempotent ingestion of finalized spool records; no raw pipeline event table."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from voice_runtime.contracts.evidence import (
    EvidenceBatch,
    ExchangeRecord,
    MessageRecord,
    OperationEnded,
)

from voice_api.auth import require_operator
from voice_api.db import get_session
from voice_api.evidence_security import safe_evidence
from voice_api.models import ConversationMessage, Exchange, Run, TraceSpan

router = APIRouter(prefix="/api/runs", tags=["evidence"])
Session = Depends(get_session)
Operator = Depends(require_operator)


def at_ns(value: int) -> datetime:
    seconds, nanoseconds = divmod(value, 1000000000)
    return datetime(1970, 1, 1, tzinfo=UTC) + timedelta(
        seconds=seconds, microseconds=nanoseconds // 1000
    )


def verify_same(existing, fields: dict) -> None:
    if any(getattr(existing, key) != value for key, value in fields.items()):
        raise HTTPException(409, "Evidence identity conflicts with existing record")


async def store_record(session: AsyncSession, run_id: str, record) -> None:
    if isinstance(record, ExchangeRecord):
        fields = dict(
            run_id=run_id,
            sequence=record.sequence,
            origin=record.origin,
            created_at=at_ns(record.timestamp_ns),
        )
        row = await session.get(Exchange, record.exchange_id)
        if row:
            verify_same(row, fields)
        else:
            session.add(Exchange(id=record.exchange_id, **fields))
        await session.flush()
        return
    if record.exchange_id is not None:
        exchange = await session.get(Exchange, record.exchange_id)
        if exchange is None or exchange.run_id != run_id:
            raise HTTPException(422, "Evidence requires an existing exchange in this run")
    if isinstance(record, MessageRecord):
        fields = dict(
            run_id=run_id,
            exchange_id=record.exchange_id,
            sequence=record.sequence,
            role=record.role,
            content=record.content,
            source_at=record.source_timestamp,
            interrupted=record.interrupted,
            created_at=at_ns(record.timestamp_ns),
        )
        row = await session.get(ConversationMessage, record.id)
        if row:
            verify_same(row, fields)
        else:
            session.add(ConversationMessage(id=record.id, **fields))
    else:
        fields = dict(
            run_id=run_id,
            exchange_id=record.exchange_id,
            name=record.name,
            category=record.category,
            started_at=at_ns(record.started_ns),
            provider=record.provider,
            model=record.model,
            otel_trace_id=record.otel_trace_id,
            otel_span_id=record.otel_span_id,
            input_payload=record.input_payload,
        )
        row = await session.get(TraceSpan, record.operation_id)
        if row:
            verify_same(row, fields)
        else:
            row = TraceSpan(id=record.operation_id, **fields)
            session.add(row)
        if isinstance(record, OperationEnded):
            ended_at = at_ns(record.ended_ns)
            if ended_at < fields["started_at"]:
                raise HTTPException(422, "Operation end precedes start")
            completion = dict(
                ended_at=ended_at,
                duration_ms=record.duration_ms,
                status=record.status,
                attributes=record.attributes,
                output_payload=record.output_payload,
                ttfb_ms=record.ttfb_ms,
                ttfa_ms=record.ttfa_ms,
                ttfat_ms=record.ttfat_ms,
                prompt_tokens=record.prompt_tokens,
                completion_tokens=record.completion_tokens,
                reasoning_tokens=record.reasoning_tokens,
                audio_seconds=record.audio_seconds,
            )
            if row.ended_at is not None:
                verify_same(row, completion)
            else:
                for key, value in completion.items():
                    setattr(row, key, value)
        elif row.ended_at is None:
            if row.attributes is not None:
                verify_same(row, {"attributes": record.attributes})
            row.attributes = record.attributes
    await session.flush()


@router.post("/{run_id}/evidence")
async def ingest(
    run_id: str, body: EvidenceBatch, session: AsyncSession = Session, _: None = Operator
) -> dict:
    if any(record.run_id != run_id for record in body.records):
        raise HTTPException(422, "Batch contains evidence for another run")
    # Serialize batches per run; retries see committed records before making changes.
    if await session.get(Run, run_id, with_for_update=True) is None:
        raise HTTPException(404, "Run not found")
    try:
        for record in body.records:
            record = type(record).model_validate(safe_evidence(record.model_dump()))
            await store_record(session, run_id, record)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(409, "Evidence conflicts with database ordering or ownership") from None
    except Exception:
        await session.rollback()
        raise
    return {"accepted": len(body.records)}
