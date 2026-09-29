"""Persistence helpers for asynchronous outcomes queued to a future user turn."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from voice_api.db.tenant_scope import required_organization
from voice_api.models import RunContextEvent


async def enqueue_context_event(
    session: AsyncSession,
    *,
    run_id: str,
    dedupe_key: str,
    source: str,
    payload: dict,
    tool_invocation_id: str | None = None,
    source_reference: str | None = None,
    connection_id: str | None = None,
    provider_message_id: str | None = None,
    status: str = "pending",
    occurred_at: datetime | None = None,
) -> RunContextEvent:
    """Idempotently persist a bounded, already-sanitized model-visible outcome."""
    org_id = required_organization(session.sync_session)
    event = await session.scalar(
        select(RunContextEvent).where(
            RunContextEvent.run_id == run_id,
            RunContextEvent.dedupe_key == dedupe_key,
        )
    )
    if event is not None:
        return event
    try:
        async with session.begin_nested():
            event = RunContextEvent(
                id=uuid4().hex,
                org_id=org_id,
                run_id=run_id,
                tool_invocation_id=tool_invocation_id,
                dedupe_key=dedupe_key,
                source=source,
                source_reference=source_reference,
                connection_id=connection_id,
                provider_message_id=provider_message_id,
                payload=payload,
                status=status,
                occurred_at=occurred_at or datetime.now(UTC),
            )
            session.add(event)
            await session.flush()
    except IntegrityError:
        event = await session.scalar(
            select(RunContextEvent).where(
                RunContextEvent.run_id == run_id,
                RunContextEvent.dedupe_key == dedupe_key,
            )
        )
        if event is None:
            raise
    return event
