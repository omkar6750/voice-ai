"""Persist a telephone request and its immutable destination before any external action."""

from datetime import timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from voice_api.models import (
    AgentVersion,
    Call,
    Contact,
    IntegrationConnection,
    Run,
    RuntimeEndpoint,
)
from voice_api.models.common import new_id, now
from voice_api.schemas.call import TelephonySelection
from voice_api.services.resolution_service import resolve
from voice_api.services.twilio_service import validate_from_number

TWILIO_STATUS_MAP = {
    "queued": "queued",
    "initiated": "dialing",
    "ringing": "ringing",
    "in-progress": "active",
    "completed": "completed",
    "busy": "failed",
    "failed": "failed",
    "no-answer": "failed",
    "canceled": "canceled",
}


async def queue_call(
    session: AsyncSession,
    contact_id: str,
    agent_version_id: str,
    endpoint_id: str | None = None,
    logging_override: bool | None = None,
    telephony: TelephonySelection | None = None,
) -> tuple[Run, Call]:
    contact = await session.get(Contact, contact_id)
    version = await session.get(AgentVersion, agent_version_id)
    if contact is None or version is None or version.status != "published":
        raise HTTPException(422, "Call requires contact and published agent")

    provider = "sim7600"
    resolved_endpoint_id = endpoint_id
    telephony_connection_id = None
    from_number = None
    provider_metadata: dict[str, Any] = {}

    if telephony and telephony.provider == "twilio":
        provider = "twilio"
        resolved_endpoint_id = None
        if not telephony.connection_id:
            raise HTTPException(422, "Twilio call requires connection_id")
        if not telephony.from_number:
            raise HTTPException(422, "Twilio call requires from_number")

        connection = await session.get(IntegrationConnection, telephony.connection_id)
        if connection is None or connection.provider != "twilio_voice":
            raise HTTPException(422, "Twilio connection not found")
        if not connection.enabled:
            raise HTTPException(422, "Twilio connection is disabled")
        if (connection.config or {}).get("account_type") == "Trial":
            raise HTTPException(422, "Twilio trial accounts cannot place Media Stream calls")

        selected_number = validate_from_number(connection, telephony.from_number)
        telephony_connection_id = connection.id
        from_number = telephony.from_number
        provider_metadata = {
            "from_number": from_number,
            "phone_number_sid": selected_number.get("sid"),
        }
    else:
        if telephony and telephony.endpoint_id:
            resolved_endpoint_id = telephony.endpoint_id
        if (
            resolved_endpoint_id
            and await session.get(RuntimeEndpoint, resolved_endpoint_id) is None
        ):
            raise HTTPException(422, "Runtime endpoint not found")

    config, digest = await resolve(session, version, logging_override)
    run = Run(
        id=new_id(),
        channel="phone",
        transport_provider=provider,
        status="queued",
        agent_version_id=version.id,
        endpoint_id=resolved_endpoint_id,
        contact_id=contact.id,
        resolved_config=config,
        config_hash=digest,
        snapshot_schema_version=1,
        contact_snapshot={
            "id": contact.id,
            "name": contact.name,
            "timezone": contact.timezone,
            "phone_number": contact.phone_number,
            "business": contact.business,
            "source": contact.source,
            "language": contact.language,
            "metadata_json": contact.metadata_json or {},
        },
    )
    session.add(run)
    await session.flush()

    call = Call(
        id=new_id(),
        correlation_id=new_id(),
        run_id=run.id,
        contact_id=contact.id,
        agent_version_id=version.id,
        target_snapshot=contact.phone_number,
        status="queued",
        provider=provider,
        telephony_connection_id=telephony_connection_id,
        from_number=from_number,
        provider_metadata=provider_metadata,
    )
    session.add(call)
    await session.flush()
    return run, call


async def get_by_correlation_id(session: AsyncSession, correlation_id: str) -> Call | None:
    return await session.scalar(select(Call).where(Call.correlation_id == correlation_id))


async def atomically_claim_run(
    session: AsyncSession,
    run_id: str,
    *,
    claim_token: str | None = None,
    lease_seconds: int = 300,
) -> bool:
    token = claim_token or new_id()
    current_time = now()
    expires_at = current_time + timedelta(seconds=lease_seconds)

    stmt = (
        update(Run)
        .where(Run.id == run_id, Run.status == "queued")
        .values(
            status="claimed",
            claim_token=token,
            claimed_at=current_time,
            lease_expires_at=expires_at,
        )
    )
    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount == 1


async def attach_twilio_media(
    session: AsyncSession,
    call: Call,
    *,
    provider_call_id: str,
    stream_sid: str,
) -> None:
    call.provider_call_id = provider_call_id
    meta = dict(call.provider_metadata or {})
    meta["stream_sid"] = stream_sid
    meta["stream_status"] = "started"
    meta["twilio_status"] = "in-progress"
    call.provider_metadata = meta
    flag_modified(call, "provider_metadata")
    call.status = "active"
    if not call.started_at:
        call.started_at = now()
    if not call.answered_at:
        call.answered_at = now()

    if call.run_id:
        run = await session.get(Run, call.run_id)
        if run and run.status == "claimed":
            run.status = "running"
            if not run.started_at:
                run.started_at = now()

    await session.commit()


async def apply_twilio_call_status(
    session: AsyncSession,
    call: Call,
    twilio_status: str | None,
    *,
    sequence_number: int | None = None,
) -> None:
    if sequence_number is not None and sequence_number < 0:
        raise ValueError("sequence_number must be nonnegative")
    if not twilio_status or not isinstance(twilio_status, str):
        return
    raw_status = twilio_status.lower()
    norm = TWILIO_STATUS_MAP.get(raw_status)
    if norm is None:
        return

    # Callback delivery order is independent of Twilio's event order. Refresh the
    # identity map after acquiring the row lock so concurrent callbacks serialize.
    locked_call = await session.get(
        Call, call.id, with_for_update=True, populate_existing=True
    )
    if locked_call is None:
        locked_call = call
    current_meta = dict(locked_call.provider_metadata or {})
    previous_sequence = current_meta.get("twilio_sequence_number")
    if sequence_number is not None and previous_sequence is not None:
        if sequence_number <= previous_sequence:
            return

    current_status = locked_call.status
    terminal = {"completed", "failed", "canceled"}
    ranks = {"queued": 0, "dialing": 1, "ringing": 2, "active": 3}
    if current_status in terminal:
        if norm != current_status:
            return
    elif norm in terminal:
        pass
    elif ranks.get(norm, -1) < ranks.get(current_status, -1):
        return

    # Keep the caller's ORM instance as the object being updated. Callers can
    # retain this instance for subsequent work; get() is used for lock/refresh.
    call.status = norm
    meta = current_meta
    meta["twilio_status"] = raw_status
    meta["twilio_raw_status"] = raw_status
    if sequence_number is not None:
        meta["twilio_sequence_number"] = sequence_number
    call.provider_metadata = meta
    flag_modified(call, "provider_metadata")

    if norm == "active":
        if not call.answered_at:
            call.answered_at = now()
        if not call.started_at:
            call.started_at = now()
    elif norm in terminal:
        if not call.ended_at:
            call.ended_at = now()
        if call.run_id:
            run = await session.get(Run, call.run_id)
            if run and run.status not in terminal:
                if run.status in {"queued", "claimed"}:
                    run.status = "failed"
                    if not run.error:
                        run.error = f"Twilio call ended with status: {raw_status}"
                    run.ended_at = run.ended_at or now()
                # A provider hangup says nothing about the agent's business result.
                # Running Runs remain owned by native runtime finalization.

    await session.commit()


async def apply_twilio_stream_status(
    session: AsyncSession,
    call: Call,
    *,
    stream_sid: str | None,
    event: str | None,
    error: str | None,
) -> None:
    meta = dict(call.provider_metadata or {})
    if stream_sid:
        meta["stream_sid"] = stream_sid
    if event == "stream-started":
        meta["stream_status"] = "started"
    elif event == "stream-stopped":
        meta["stream_status"] = "stopped"
    elif event == "stream-error":
        meta["stream_status"] = "error"
        if error:
            meta["stream_error"] = error
    call.provider_metadata = meta
    flag_modified(call, "provider_metadata")
    await session.commit()
