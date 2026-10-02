"""Locally queue classifier outcomes; deliver through the evidence channel."""

from uuid import NAMESPACE_URL, uuid5


class NativeEvidenceRuntime:
    async def _persist_context_event(
        self,
        invocation_id,
        dedupe_key,
        source,
        source_reference,
        payload,
        *,
        connection_id=None,
        provider_message_id=None,
    ):
        event = {
            "id": str(uuid5(NAMESPACE_URL, f"{self.run_id}/{dedupe_key}")),
            "dedupe_key": dedupe_key,
            "source": source,
            "source_reference": source_reference,
            "payload": self._bounded_context_result(payload),
            "tool_invocation_id": invocation_id,
            "connection_id": connection_id,
            "provider_message_id": provider_message_id,
            "status": "ended_before_delivery" if self._call_closed else "pending",
        }
        self.pending_context[event["id"]] = event
        if getattr(self, "broker", None):
            await self.broker.context_update({"enqueue": event})
