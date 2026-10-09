"""Authenticated text-test setup and history; execution remains in runtime."""

import asyncio
import time
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from voice_api.api.deps import get_session, require_legacy_owner
from voice_api.core.security import allow_organization_member
from voice_api.models import (
    ChatConversation,
    ChatMessage,
    FlowNodeVisit,
    RuntimeAssignment,
    ToolInvocation,
    TraceSpan,
)
from voice_api.schemas.chat import ChatSummary, ChatTestTurn, ChatTicket, CreateChat
from voice_api.services import chat_service
from voice_api.services.evidence_service import related_evidence
from voice_api.services.runtime_dispatch import control, identity, stop

router = APIRouter(prefix="/chat-conversations", tags=["chat-tests"])
Session = Depends(get_session)
Actor = Depends(require_legacy_owner)


@router.post("", response_model=ChatSummary, status_code=201)
@allow_organization_member
async def create(body: CreateChat, session=Session, actor=Actor):
    return chat_service.summary(await chat_service.create(session, body))


async def collect_test_turn(
    session,
    conversation_id,
    run_id,
    assignment,
    *,
    after_sequence=0,
    caller_message=None,
):
    """Collect the persisted response and execution evidence for one caller turn."""
    if caller_message is not None:
        await control(
            "/v1/sessions/text-command",
            {
                **identity(assignment),
                "id": str(uuid4()),
                "type": "user_message",
                "text": caller_message,
            },
        )
    deadline = time.monotonic() + 90
    last_change = time.monotonic()
    cursor = after_sequence
    events, pending_tools = [], set()
    has_assistant = has_error = False
    while time.monotonic() < deadline:
        # Runtime persists messages in a separate transaction. End each read
        # transaction so the next poll sees newly committed rows even under
        # repeatable-read, while retaining this request's verified tenant scope.
        rows = (
            await session.scalars(
                select(ChatMessage)
                .where(
                    ChatMessage.conversation_id == conversation_id,
                    ChatMessage.run_id == run_id,
                    ChatMessage.sequence > cursor,
                )
                .order_by(ChatMessage.sequence)
            )
        ).all()
        await session.commit()
        if rows:
            last_change = time.monotonic()
            for row in rows:
                cursor = max(cursor, row.sequence)
                event = {"type": "message", "kind": row.kind, "payload": row.payload}
                events.append(event)
                if row.kind == "assistant" and row.payload.get("status") == "completed":
                    has_assistant = True
                elif row.kind == "error":
                    has_error = True
                elif row.kind == "evidence":
                    record = row.payload or {}
                    invocation_id = record.get("invocation_id") or record.get("tool_invocation_id")
                    if record.get("kind") == "tool_started":
                        pending_tools.add(invocation_id or "unknown")
                    elif record.get("kind") in {"tool_result", "tool_ended"}:
                        if invocation_id:
                            pending_tools.discard(invocation_id)
                        elif pending_tools:
                            pending_tools.pop()
        if (
            (has_assistant and not pending_tools) or has_error
        ) and time.monotonic() - last_change >= 2:
            break
        await asyncio.sleep(0.5)
    return events, cursor


def compact_test_events(events):
    transcript, activity, errors, node_changes = [], [], [], []
    for event in events:
        kind = event.get("type")
        if kind == "message":
            payload = event.get("payload") or {}
            if event.get("kind") in {"user", "assistant"}:
                text = payload.get("text", "")
                if text:
                    transcript.append(
                        {"role": event["kind"], "text": text, "status": payload.get("status")}
                    )
            elif event.get("kind") == "error":
                errors.append(payload)
            elif event.get("kind") == "evidence":
                record = payload if isinstance(payload, dict) else {}
                record_kind = record.get("kind")
                if record_kind in {"tool_started", "tool_result", "tool_ended"}:
                    item = {
                        key: record[key]
                        for key in (
                            "kind",
                            "name",
                            "tool_name",
                            "tool_id",
                            "binding_key",
                            "status",
                            "invocation_id",
                            "input_payload",
                            "output_payload",
                            "result",
                            "error",
                        )
                        if key in record
                    }
                    activity.append(item)
                elif record_kind in {"flow_visit_started", "flow_visit_ended"}:
                    node_changes.append(
                        {
                            key: record[key]
                            for key in (
                                "kind",
                                "node_id",
                                "node_key",
                                "node_name",
                                "status",
                                "started_at",
                                "ended_at",
                                "started_ns",
                                "ended_ns",
                            )
                            if key in record
                        }
                    )
                elif record_kind == "diagnostic" and record.get("severity") == "error":
                    errors.append(
                        {
                            key: record[key]
                            for key in ("category", "message", "diagnostic_id", "timestamp")
                            if key in record
                        }
                    )
        elif kind == "error":
            errors.append(
                {key: event[key] for key in ("stage", "message", "diagnostic_id") if key in event}
            )
    return {
        "transcript": transcript,
        "tool_activity": activity,
        "node_changes": node_changes,
        "errors": errors,
    }


@router.post("/turn")
@allow_organization_member
async def mcp_turn(body: ChatTestTurn, session=Session, actor=Actor):
    """Create or continue a saved-config test and return only the current turn."""
    if body.agent_version_id:
        row = await chat_service.create(
            session,
            CreateChat(
                agent_version_id=body.agent_version_id,
                contact_id=body.contact_id,
                starting_node=body.starting_node,
                caller_background=body.caller_background,
                scenario=body.scenario,
            ),
        )
        created = True
        previous_run_id = None
    else:
        row = await chat_service.get_conversation(session, str(body.conversation_id))
        if row.status == "ended":
            raise HTTPException(409, "Conversation ended; start a new one from the saved draft")
        created = False
        previous_run_id = row.active_run_id

    execution = await chat_service.ticket(session, row, text_control=True)
    run_id = execution["run_id"]
    assignment = await session.get(RuntimeAssignment, run_id)
    if not assignment:
        raise HTTPException(503, "Text-test runtime assignment was not created")

    sequence = 0
    if not created and run_id == previous_run_id:
        sequence = (
            await session.scalar(
                select(func.max(ChatMessage.sequence)).where(
                    ChatMessage.run_id == run_id, ChatMessage.conversation_id == row.id
                )
            )
            or 0
        )
    events = []
    if created:
        events, sequence = await collect_test_turn(session, row.id, run_id, assignment)
        if body.caller_message and not any(event.get("kind") == "error" for event in events):
            next_turn, sequence = await collect_test_turn(
                session,
                row.id,
                run_id,
                assignment,
                after_sequence=sequence,
                caller_message=body.caller_message,
            )
            events.extend(next_turn)
    else:
        events, sequence = await collect_test_turn(
            session,
            row.id,
            run_id,
            assignment,
            after_sequence=sequence,
            caller_message=body.caller_message,
        )

    await session.refresh(row)

    result = compact_test_events(events)
    return {
        "conversation_id": row.id,
        "run_id": run_id,
        "agent_version_id": row.agent_version_id,
        "revision": row.revision,
        "status": row.status,
        "created": created,
        **result,
        "turn_timed_out": not any(item["role"] == "assistant" for item in result["transcript"])
        and not result["errors"],
    }


@router.get("", response_model=list[ChatSummary])
@allow_organization_member
async def listing(agent_version_id: str, session=Session, actor=Actor):
    rows = (
        await session.scalars(
            select(ChatConversation)
            .where(ChatConversation.agent_version_id == agent_version_id)
            .order_by(ChatConversation.created_at.desc())
            .limit(100)
        )
    ).all()
    return [chat_service.summary(row) for row in rows]


@router.get("/{conversation_id}")
@allow_organization_member
async def detail(conversation_id: str, session=Session, actor=Actor):
    row = await chat_service.get_conversation(session, conversation_id)
    messages = (
        await session.scalars(
            select(ChatMessage)
            .where(ChatMessage.conversation_id == row.id)
            .order_by(ChatMessage.created_at, ChatMessage.sequence)
        )
    ).all()

    def display(message):
        payload = dict(message.payload)
        if message.kind == "evidence":
            payload.pop("input_payload", None)
            payload.pop("output_payload", None)
        return {
            "id": message.id,
            "run_id": message.run_id,
            "sequence": message.sequence,
            "kind": message.kind,
            "payload": payload,
        }

    return {
        **chat_service.summary(row),
        "messages": [display(m) for m in messages],
        "can_resume": bool(row.checkpoint and row.checkpoint.get("safe")),
    }


@router.post("/{conversation_id}/ticket", response_model=ChatTicket)
@allow_organization_member
async def ticket(conversation_id: str, session=Session, actor=Actor):
    return await chat_service.ticket(
        session, await chat_service.get_conversation(session, conversation_id)
    )


@router.post("/{conversation_id}/end")
@allow_organization_member
async def end(conversation_id: str, session=Session, actor=Actor):
    row = await chat_service.get_conversation(session, conversation_id)
    if row.active_run_id:
        try:
            await stop(session, row.active_run_id)
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
    row.status = "ended"
    await session.commit()
    return {"status": "ended"}


@router.get("/{conversation_id}/messages/{message_id}")
@allow_organization_member
async def inspect(conversation_id: str, message_id: str, session=Session, actor=Actor):
    row = await chat_service.get_conversation(session, conversation_id)
    message = await session.get(ChatMessage, message_id)
    if not message or message.conversation_id != row.id:
        raise HTTPException(404, "Message evidence not found; it may still be saving")
    evidence = await related_evidence(session, message.run_id)
    operation_id = message.payload.get("operation_id") or message.payload.get("llm_operation_id")
    visit_id = message.payload.get("visit_id")
    if visit_id:
        visit = await session.get(FlowNodeVisit, visit_id)
        if visit and visit.run_id == message.run_id:
            operation_id = visit.span_id
    attributes = message.payload.get("attributes") or {}
    invocation_id = message.payload.get("invocation_id") or (
        attributes.get("tool_invocation_id") if isinstance(attributes, dict) else None
    )
    tool = await session.get(ToolInvocation, invocation_id) if invocation_id else None
    if tool and tool.run_id != message.run_id:
        tool = None
    operation_id = operation_id or (tool.llm_operation_id if tool else None)
    if operation_id:
        descendants = (
            select(TraceSpan.id)
            .where(TraceSpan.run_id == message.run_id, TraceSpan.id == operation_id)
            .cte("chat_operation_tree", recursive=True)
        )
        descendants = descendants.union_all(
            select(TraceSpan.id).where(
                TraceSpan.run_id == message.run_id, TraceSpan.parent_id == descendants.c.id
            )
        )
        span_filter = TraceSpan.id.in_(select(descendants.c.id))
    else:
        span_filter = TraceSpan.exchange_id == message.payload.get("exchange_id")
    spans = (
        await session.scalars(
            select(TraceSpan)
            .where(
                TraceSpan.run_id == message.run_id,
                span_filter,
            )
            .order_by(TraceSpan.started_at)
        )
    ).all()
    return {
        "message": message.payload,
        "kind": message.kind,
        "tool": {
            key: getattr(tool, key, None)
            for key in (
                "id",
                "binding_key",
                "arguments",
                "result",
                "status",
                "started_at",
                "ended_at",
                "llm_operation_id",
            )
        }
        if tool
        else None,
        "evidence": evidence,
        "operations": [
            {
                key: getattr(span, key, None)
                for key in (
                    "id",
                    "name",
                    "category",
                    "provider",
                    "model",
                    "status",
                    "input_payload",
                    "output_payload",
                    "started_at",
                    "ended_at",
                    "duration_ms",
                    "prompt_tokens",
                    "completion_tokens",
                    "total_tokens",
                    "attributes",
                )
            }
            for span in spans
        ],
    }
