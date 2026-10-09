"""Text conversation setup and commit-before-acknowledgement persistence."""

from copy import deepcopy
from datetime import timedelta
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from voice_runtime.execution.redaction import redact

from voice_api.models import (
    AgentVersion,
    ChatConversation,
    ChatExecution,
    ChatMessage,
    Contact,
    Run,
    RuntimeAssignment,
)
from voice_api.models.common import now
from voice_api.services.resolution_service import fingerprint, resolve
from voice_api.services.runtime_dispatch import control, dispatch, identity


def summary(row):
    return dict(
        id=row.id,
        agent_version_id=row.agent_version_id,
        revision=row.revision,
        status=row.status,
        scenario=row.scenario,
        destination=row.contact_snapshot.get("phone_number", ""),
        created_at=row.created_at.isoformat(),
        error=row.error,
    )


async def get_conversation(session, conversation_id, *, lock=False):
    row = await session.get(
        ChatConversation, conversation_id, with_for_update=lock, populate_existing=True
    )
    if not row:
        raise HTTPException(404, "Chat conversation not found")
    return row


async def create(session, body):
    version = await session.get(AgentVersion, str(body.agent_version_id))
    if not version or version.status not in {"draft", "published"}:
        raise HTTPException(422, "Select a saved draft or published version")
    contact = await session.get(Contact, str(body.contact_id)) if body.contact_id else None
    if body.contact_id and not contact:
        raise HTTPException(404, "Contact not found")
    snapshot, _ = await resolve(session, version, text_test=True)
    snapshot = deepcopy(snapshot)
    node = body.starting_node or snapshot["flow"]["initial_node"]
    if node not in {n["id"] for n in snapshot["flow"]["nodes"]}:
        raise HTTPException(422, "Starting node is absent from the saved configuration")
    snapshot["flow"]["initial_node"] = node
    snapshot["_text_test"] = True
    snapshot["_caller_background"] = body.caller_background
    snapshot["agent_version_id"] = version.id
    contact_data = (
        {
            k: getattr(contact, k, None)
            for k in (
                "id",
                "first_name",
                "last_name",
                "timezone",
                "phone_number",
                "business",
                "source",
                "language",
            )
        }
        if contact
        else {}
    )
    contact_data["metadata_json"] = dict(contact.metadata_json or {}) if contact else {}
    if body.whatsapp_number:
        contact_data["phone_number"] = body.whatsapp_number
    snapshot["_resolved"]["contact"] = contact_data
    snapshot["contact_snapshot"] = contact_data
    snapshot["contact_id"] = contact.id if contact else None
    snapshot["target_snapshot"] = contact_data.get("phone_number", "")
    row = ChatConversation(
        id=str(uuid4()),
        agent_version_id=version.id,
        revision=version.revision,
        snapshot=snapshot,
        contact_id=contact.id if contact else None,
        contact_snapshot=contact_data,
        scenario=body.scenario,
        status="created",
    )
    session.add(row)
    await session.commit()
    return row


async def ticket(session, row, *, text_control=False):
    row = await get_conversation(session, row.id, lock=True)
    if row.status == "ended":
        raise HTTPException(409, "Conversation ended; start a new conversation")
    if row.active_run_id:
        assignment = await session.get(RuntimeAssignment, row.active_run_id)
        if (
            assignment
            and assignment.state in {"starting", "active"}
            and assignment.lease_expires_at > now()
        ):
            try:
                path = "/v1/sessions/text-start" if text_control else "/v1/sessions/text-ticket"
                result = await control(path, identity(assignment))
                return {**result, "run_id": row.active_run_id, "conversation_id": row.id}
            except HTTPException as exc:
                if exc.status_code != 404:
                    raise
                # A restarted runtime cannot resume an old execution.
                assignment.state = "ended"
        elif assignment and assignment.state == "preparing":
            raise HTTPException(409, "Conversation setup is already in progress")
    if row.active_run_id and not assignment:
        # The API may have stopped after saving the attempt but before preparation.
        # No assignment means no runtime received credentials or execution authority.
        if row.status == "connecting" and row.updated_at > now() - timedelta(seconds=60):
            raise HTTPException(409, "Conversation setup is still in progress; retry shortly")
        previous_run = await session.get(Run, row.active_run_id, with_for_update=True)
        has_messages = await session.scalar(
            select(ChatMessage.id).where(ChatMessage.run_id == row.active_run_id).limit(1)
        )
        if (
            not has_messages
            and previous_run
            and previous_run.status in {"queued", "claimed", "failed"}
        ):
            previous_run.status = "failed"
            previous_run.error = "Chat setup did not reach runtime preparation"
            row.active_run_id = None
    if row.active_run_id and not row.checkpoint:
        raise HTTPException(
            409, "No safe checkpoint is available. History is readable; start a new conversation."
        )
    if row.checkpoint and not row.checkpoint.get("safe", False):
        raise HTTPException(
            409,
            "An external action is unresolved. Inspect its outcome before starting a new conversation.",
        )
    resume_checkpoint = deepcopy(row.checkpoint)
    run = Run(
        channel="text_test",
        transport_provider="text",
        agent_version_id=row.agent_version_id,
        contact_id=row.contact_id,
        # Dispatch compiles and freezes configuration before claiming execution.
        status="queued",
        resolved_config=deepcopy(row.snapshot),
        contact_snapshot=row.contact_snapshot,
        snapshot_schema_version=1,
        config_hash=fingerprint(row.snapshot),
    )
    session.add(run)
    await session.flush()
    session.add(ChatExecution(conversation_id=row.id, run_id=run.id))
    row.active_run_id = run.id
    row.status = "connecting"
    row.checkpoint = {**(row.checkpoint or {}), "safe": False} if row.checkpoint else None
    row.error = None
    await session.commit()
    conversation_id, run_id = row.id, run.id
    try:
        assignment = await dispatch(
            session, run, conversation_id=row.id, checkpoint=resume_checkpoint
        )
        path = "/v1/sessions/text-start" if text_control else "/v1/sessions/text-ticket"
        result = await control(path, identity(assignment))
    except Exception as exc:
        # A database failure leaves the transaction unusable until rollback.
        await session.rollback()
        row = await get_conversation(session, conversation_id, lock=True)
        run = await session.get(Run, run_id, with_for_update=True)
        assignment = await session.get(RuntimeAssignment, run_id)
        if not assignment or assignment.state == "rejected":
            run.status = "failed"
            row.checkpoint = resume_checkpoint
        row.status = "failed"
        row.error = {
            "stage": "setup",
            "diagnostic_id": str(uuid4()),
            "message": "Chat setup failed. Check runtime availability, capacity and saved provider configuration.",
            "timestamp": now().isoformat(),
        }
        run.error = row.error["message"]
        await session.commit()
        if isinstance(exc, HTTPException):
            raise HTTPException(
                exc.status_code,
                {
                    **row.error,
                    "message": exc.detail if isinstance(exc.detail, str) else row.error["message"],
                },
            ) from None
        raise HTTPException(503, row.error) from None
    return {**result, "run_id": run.id, "conversation_id": row.id}


async def persist_batch(session, run, records, checkpoint, lifecycle):
    attempt = await session.scalar(select(ChatExecution).where(ChatExecution.run_id == run.id))
    if not attempt:
        raise HTTPException(422, "Text execution is not assigned to a conversation")
    row = await get_conversation(session, attempt.conversation_id, lock=True)
    active_attempt = row.active_run_id == run.id
    for record in records:
        if not isinstance(record.get("id"), str) or record.get("kind") not in {
            "user",
            "assistant",
            "error",
            "evidence",
            "state",
        }:
            raise HTTPException(422, "Invalid chat record")
        previous = await session.get(ChatMessage, record["id"])
        if previous:
            if previous.run_id != run.id or previous.sequence != record["sequence"]:
                raise HTTPException(409, "Chat record identity conflict")
            continue
        session.add(
            ChatMessage(
                id=record["id"],
                conversation_id=row.id,
                run_id=run.id,
                sequence=record["sequence"],
                kind=record["kind"],
                payload=redact(record["payload"]),
            )
        )
        if record["kind"] == "error":
            row.error = redact(record["payload"])
    if checkpoint and active_attempt:
        row.checkpoint = redact(checkpoint)
    state = lifecycle.get("chat_state")
    if (
        active_attempt
        and row.status != "ended"
        and state in {"connected", "paused", "ended", "failed"}
    ):
        row.status = state
    return len(records)
