"""Persistence of runtime evidence associated with contextual events."""

from __future__ import annotations


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
        from voice_api.db.session import SessionFactory
        from voice_api.db.tenant_scope import bind_run_organization
        from voice_api.services.run_context_service import enqueue_context_event

        async with SessionFactory() as session:
            await bind_run_organization(session, self.run_id)
            await enqueue_context_event(
                session,
                run_id=self.run_id,
                tool_invocation_id=invocation_id,
                dedupe_key=dedupe_key,
                source=source,
                source_reference=source_reference,
                connection_id=connection_id,
                provider_message_id=provider_message_id,
                status="ended_before_delivery" if self._call_closed else "pending",
                payload=self._bounded_context_result(payload),
            )
            await session.commit()
