"""Delivery and consumption tracking for asynchronous context events."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from pipecat.processors.aggregators.llm_context import LLMContext


class NativeContextDelivery:
    @staticmethod
    def _bounded_context_result(value: Any) -> Any:
        import json

        def clean(item):
            if isinstance(item, dict):
                private = {
                    "source_path",
                    "file_path",
                    "access_token",
                    "api_key",
                    "authorization",
                    "headers",
                    "secret",
                    "secret_reference",
                }
                return {
                    str(k): clean(v)
                    for k, v in item.items()
                    if not str(k).startswith("_") and str(k).lower() not in private
                }
            if isinstance(item, list):
                return [clean(v) for v in item[:20]]
            if isinstance(item, str):
                return item[:3000]
            if item is None or isinstance(item, (bool, int, float)):
                return item
            return str(item)[:300]

        result = clean(value)
        if len(json.dumps(result, ensure_ascii=False, separators=(",", ":"))) > 6000:
            return {"status": "error", "error": "Tool result exceeded the context size limit."}
        return result

    async def _deliver_pending_context_events(self, context: LLMContext) -> None:
        if context is None:
            return

        from sqlalchemy import select
        from voice_api.db.session import SessionFactory
        from voice_api.db.tenant_scope import bind_run_organization
        from voice_api.models import RunContextEvent

        async with SessionFactory() as session:
            await bind_run_organization(session, self.run_id)
            events = (
                await session.scalars(
                    select(RunContextEvent)
                    .where(
                        RunContextEvent.run_id == self.run_id, RunContextEvent.status == "pending"
                    )
                    .order_by(RunContextEvent.occurred_at, RunContextEvent.id)
                    .limit(50)
                    .with_for_update(skip_locked=True)
                )
            ).all()
            messages = context.get_messages()
            for event in events:
                marker = f"[[voice-ai-context-event:{event.id}]]"
                message_index = next(
                    (
                        index
                        for index, message in enumerate(messages)
                        if marker in str(message.get("content", ""))
                    ),
                    None,
                )
                if message_index is None:
                    messages.append(
                        {
                            "role": "system",
                            "content": (
                                marker
                                + "\nEvidence-backed asynchronous outcome: "
                                + json.dumps(
                                    event.payload, ensure_ascii=False, separators=(",", ":")
                                )
                                + ". Report only the status shown here. Meta acceptance is not proof of delivery; a delivery claim requires a delivered/read receipt."
                            ),
                        }
                    )
                    message_index = len(messages) - 1
                context.set_messages(messages)
                event.status = "delivered"
                event.delivered_at = datetime.now(UTC)
                event.context_message_index = message_index
            if events:
                await session.commit()

    async def _mark_context_events_consumed(self, messages, exchange_id, operation_id):

        from sqlalchemy import select
        from voice_api.db.session import SessionFactory
        from voice_api.db.tenant_scope import bind_run_organization
        from voice_api.models import RunContextEvent

        serialized = "\n".join(str(message.get("content", "")) for message in messages)
        async with SessionFactory() as session:
            await bind_run_organization(session, self.run_id)
            events = (
                await session.scalars(
                    select(RunContextEvent).where(
                        RunContextEvent.run_id == self.run_id, RunContextEvent.status == "delivered"
                    )
                )
            ).all()
            changed = False
            for event in events:
                if f"[[voice-ai-context-event:{event.id}]]" in serialized:
                    event.status = "consumed"
                    event.consumed_at = datetime.now(UTC)
                    event.consumed_exchange_id = exchange_id
                    event.consuming_span_id = operation_id
                    changed = True
            if changed:
                await session.commit()
