"""Keep the retained in-process API path functional until remote activation.

This compatibility broker is API-only. The independent runtime never imports it.
"""

from sqlalchemy import select

from voice_api.db.session import SessionFactory
from voice_api.db.tenant_scope import bind_run_organization
from voice_api.models import RunContextEvent
from voice_api.models.common import now
from voice_api.services.run_context_service import enqueue_context_event
from voice_api.services.runtime_tools import BackendToolDispatch


class LegacyRuntimeBroker:
    def __init__(self, host):
        self.host = host

    async def tool(self, name, args, invocation_id):
        adapter = BackendToolDispatch()
        adapter.run_id = self.host.run_id
        adapter._snapshot = self.host._snapshot
        adapter.settings = self.host.settings
        return await adapter._handler(name)(args, self.host.flow)

    async def context_update(self, update):
        async with SessionFactory() as session:
            await bind_run_organization(session, self.host.run_id)
            if "enqueue" in update:
                data = update["enqueue"]
                event = await enqueue_context_event(
                    session,
                    run_id=self.host.run_id,
                    dedupe_key=data["dedupe_key"],
                    source=data["source"],
                    payload=data["payload"],
                    tool_invocation_id=data.get("tool_invocation_id"),
                    source_reference=data.get("source_reference"),
                    connection_id=data.get("connection_id"),
                    provider_message_id=data.get("provider_message_id"),
                    status=data["status"],
                )
                event.id = data["id"]
            else:
                event = await session.get(RunContextEvent, update["id"])
                if event and event.run_id == self.host.run_id:
                    event.status = update["status"]
                    if event.status == "delivered":
                        event.delivered_at = now()
                        event.context_message_index = update.get("context_message_index")
                    if event.status == "consumed":
                        event.consumed_at = now()
                        event.consumed_exchange_id = update.get("exchange_id")
                        event.consuming_span_id = update.get("operation_id")
            await session.commit()

    async def refresh_context(self):
        async with SessionFactory() as session:
            await bind_run_organization(session, self.host.run_id)
            events = (
                await session.scalars(
                    select(RunContextEvent)
                    .where(
                        RunContextEvent.run_id == self.host.run_id,
                        RunContextEvent.status == "pending",
                    )
                    .order_by(RunContextEvent.occurred_at)
                    .limit(50)
                )
            ).all()
            for event in events:
                self.host.pending_context.setdefault(
                    event.id, {"id": event.id, "status": "pending", "payload": event.payload}
                )
