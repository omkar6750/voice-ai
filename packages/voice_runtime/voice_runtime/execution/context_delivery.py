"""Delivery and consumption tracking for asynchronous context events."""

from __future__ import annotations

import json
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
        messages = context.get_messages()
        for event in getattr(self, "pending_context", {}).values():
            if event["status"] != "pending":
                continue
            marker = f"[[voice-ai-context-event:{event['id']}]]"
            messages.append(
                {
                    "role": "system",
                    "content": marker
                    + "\nEvidence-backed asynchronous outcome: "
                    + json.dumps(event["payload"], ensure_ascii=False)
                    + ". Report only this status; acceptance is not delivery.",
                }
            )
            event["status"] = "delivered"
            if getattr(self, "broker", None):
                await self.broker.context_update(
                    {
                        "id": event["id"],
                        "status": "delivered",
                        "context_message_index": len(messages) - 1,
                    }
                )
        context.set_messages(messages)

    async def _mark_context_events_consumed(self, messages, exchange_id, operation_id):
        serialized = "\n".join(str(message.get("content", "")) for message in messages)
        for event in getattr(self, "pending_context", {}).values():
            if (
                event["status"] == "delivered"
                and f"[[voice-ai-context-event:{event['id']}]]" in serialized
            ):
                event["status"] = "consumed"
                if getattr(self, "broker", None):
                    await self.broker.context_update(
                        {
                            "id": event["id"],
                            "status": "consumed",
                            "exchange_id": exchange_id,
                            "operation_id": operation_id,
                        }
                    )
