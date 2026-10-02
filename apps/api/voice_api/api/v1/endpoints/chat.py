"""Authenticated text-test setup and history; execution remains in runtime."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from voice_api.api.deps import get_session, require_legacy_owner
from voice_api.core.security import allow_organization_member
from voice_api.models import ChatConversation, ChatMessage, TraceSpan
from voice_api.schemas.chat import ChatSummary, ChatTicket, CreateChat
from voice_api.services import chat_service
from voice_api.services.evidence_service import related_evidence
from voice_api.services.runtime_dispatch import stop

router = APIRouter(prefix="/chat-conversations", tags=["chat-tests"])
Session = Depends(get_session)
Actor = Depends(require_legacy_owner)


@router.post("", response_model=ChatSummary, status_code=201)
@allow_organization_member
async def create(body: CreateChat, session=Session, actor=Actor):
    return chat_service.summary(await chat_service.create(session, body))


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
    spans = (
        await session.scalars(
            select(TraceSpan).where(
                TraceSpan.run_id == message.run_id,
                TraceSpan.id == operation_id
                if operation_id
                else TraceSpan.exchange_id == message.payload.get("exchange_id"),
            )
        )
    ).all()
    return {
        "message": message.payload,
        "kind": message.kind,
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
