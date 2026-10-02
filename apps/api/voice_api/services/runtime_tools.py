"""Tool dispatch and integration credential resolution for the call host."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from voice_runtime.diagnostics import (
    exception_diagnostic,
    provider_error_diagnostic,
)
from voice_runtime.execution.credential_keys import stage_api_key
from voice_runtime.safe_logs import RuntimeEvent, error_category, opaque_id, operational_event

from voice_api.services.runtime_tool_helpers import (
    _provider_body,
    _retry_after,
    build_whatsapp_template_payload,
)

FlowManager = Any


class BackendToolDispatch:
    async def _whatsapp_runtime_config(
        self,
        *,
        connection_id: str | None = None,
    ) -> tuple[str, str, str | None, str]:
        """Resolve a pinned integration; template media IDs are already provider IDs."""
        access_token = ""
        phone_number_id = ""
        if connection_id:
            # An explicitly pinned tool must fail closed instead of falling back
            # to unrelated process-wide WhatsApp credentials.
            access_token = ""
            phone_number_id = ""
        api_version = "v21.0"
        try:
            from sqlalchemy import select

            from voice_api.db.session import SessionFactory
            from voice_api.db.tenant_scope import bind_run_organization
            from voice_api.models import (
                IntegrationConnection,
                ProviderCredential,
            )
            from voice_api.services.vault_service import CredentialVault

            async with SessionFactory() as session:
                await bind_run_organization(session, self.run_id)
                query = select(IntegrationConnection).where(
                    IntegrationConnection.provider == "whatsapp",
                    IntegrationConnection.enabled.is_(True),
                    IntegrationConnection.deleted_at.is_(None),
                )
                if connection_id:
                    query = query.where(IntegrationConnection.id == connection_id)
                elif phone_number_id:
                    query = query.where(
                        IntegrationConnection.config["phone_number_id"].astext == phone_number_id
                    )
                rows = (
                    await session.scalars(query.order_by(IntegrationConnection.created_at))
                ).all()
                row = rows[0] if rows else None
                if row is not None:
                    connection_id = str(row.id)
                    phone_number_id = str(row.config.get("phone_number_id") or "")
                    api_version = str(row.config.get("api_version") or api_version)
                    # A pinned template tool must use the secret belonging to that exact
                    # connection, never a process-wide token for another WhatsApp account.
                    if row.credential_id:
                        from voice_api.services.credential_service import credential_scope

                        credential = await session.scalar(
                            select(ProviderCredential).where(
                                ProviderCredential.id == row.credential_id,
                                ProviderCredential.org_id == row.org_id,
                            )
                        )
                        if (
                            credential is None
                            or credential.provider != "whatsapp"
                            or credential.purpose != "whatsapp_cloud"
                            or credential.status != "stored"
                        ):
                            raise RuntimeError("WhatsApp credential unavailable")
                        access_token = CredentialVault.from_env().decrypt(
                            credential.ciphertext,
                            credential.key_id,
                            scope=credential_scope(credential),
                        )
                    else:
                        raise RuntimeError("WhatsApp connection has no named provider credential")
        except Exception:
            operational_event(RuntimeEvent.INTEGRATION_FAILED, level="WARNING", provider="whatsapp")
        return (
            access_token,
            phone_number_id,
            connection_id,
            api_version,
        )

    def _handler(self, name: str):
        async def execute(args: dict, _manager: FlowManager):
            if name == "check_whatsapp_window":
                connection_id = self._snapshot["_resolved"]["tools"][name]["definition"].get(
                    "whatsapp_connection_id"
                )
                if not connection_id:
                    return {"status": "error", "error": "WhatsApp tool has no pinned connection"}
                contact = (
                    self._snapshot.get("_resolved", {}).get("contact")
                    or self._snapshot.get("contact_snapshot")
                    or {}
                )
                raw_phone = (
                    (None if self._snapshot.get("_text_test") else args.get("to"))
                    or contact.get("phone_number")
                    or contact.get("phone_e164")
                    or self._snapshot.get("target_snapshot", "")
                )
                recipient = re.sub(r"[^\d]", "", raw_phone or "")
                if not recipient:
                    return {"status": "error", "error": "No valid phone number for contact"}

                cutoff = datetime.now(UTC) - timedelta(hours=24)
                has_inbound = False
                try:
                    from sqlalchemy import select

                    from voice_api.db.session import SessionFactory
                    from voice_api.db.tenant_scope import bind_run_organization
                    from voice_api.models import InboundWebhookMessage

                    async with SessionFactory() as db_session:
                        await bind_run_organization(db_session, self.run_id)
                        inbound_row = await db_session.scalar(
                            select(InboundWebhookMessage)
                            .where(
                                InboundWebhookMessage.sender_phone == recipient,
                                InboundWebhookMessage.connection_id == connection_id,
                                InboundWebhookMessage.received_at >= cutoff,
                            )
                            .order_by(InboundWebhookMessage.received_at.desc())
                        )
                        if inbound_row is not None:
                            has_inbound = True
                except Exception as exc:
                    operational_event(
                        RuntimeEvent.INBOUND_CHECK_FAILED,
                        level="WARNING",
                        error_category=error_category(exc),
                    )

                return {
                    "status": "ok",
                    "window_open": has_inbound,
                    "recipient": recipient,
                    "reason": "Customer service window open"
                    if has_inbound
                    else "Window closed (no inbound message from contact in last 24 hours; template required)",
                }
            if name == "send_whatsapp_message":
                connection_id = self._snapshot["_resolved"]["tools"][name]["definition"].get(
                    "whatsapp_connection_id"
                )
                if not connection_id:
                    return {"status": "error", "error": "WhatsApp tool has no pinned connection"}
                contact = (
                    self._snapshot.get("_resolved", {}).get("contact")
                    or self._snapshot.get("contact_snapshot")
                    or {}
                )
                raw_phone = (
                    (None if self._snapshot.get("_text_test") else args.get("to"))
                    or contact.get("phone_number")
                    or contact.get("phone_e164")
                    or self._snapshot.get("target_snapshot", "")
                )
                recipient = re.sub(r"[^\d]", "", raw_phone)
                if not recipient:
                    return {"status": "error", "error": "No valid phone number for contact"}

                # Check if contact sent an inbound WhatsApp message within the last 24 hours
                cutoff = datetime.now(UTC) - timedelta(hours=24)
                has_inbound = False
                try:
                    from sqlalchemy import select

                    from voice_api.db.session import SessionFactory
                    from voice_api.db.tenant_scope import bind_run_organization
                    from voice_api.models import InboundWebhookMessage

                    async with SessionFactory() as db_session:
                        await bind_run_organization(db_session, self.run_id)
                        inbound_row = await db_session.scalar(
                            select(InboundWebhookMessage)
                            .where(
                                InboundWebhookMessage.sender_phone == recipient,
                                InboundWebhookMessage.connection_id == connection_id,
                                InboundWebhookMessage.received_at >= cutoff,
                            )
                            .order_by(InboundWebhookMessage.received_at.desc())
                        )
                        if inbound_row is not None:
                            has_inbound = True
                except Exception as exc:
                    operational_event(
                        RuntimeEvent.INBOUND_CHECK_FAILED,
                        level="WARNING",
                        error_category=error_category(exc),
                    )

                if not has_inbound:
                    return {
                        "status": "error",
                        "error": "Customer service window is closed (no inbound WhatsApp message received from contact in the last 24 hours). Meta requires an approved template outside this window.",
                    }

                text = (args.get("text") or args.get("message") or "").strip()
                if not text:
                    return {"status": "error", "error": "Message text cannot be empty"}

                (
                    access_token,
                    phone_number_id,
                    connection_id,
                    api_version,
                ) = await self._whatsapp_runtime_config(connection_id=connection_id)
                if not access_token or not phone_number_id:
                    operational_event(
                        RuntimeEvent.CREDENTIALS_MISSING, level="WARNING", provider="whatsapp"
                    )
                    return {
                        "status": "error",
                        "error": "WhatsApp credentials not configured on runtime",
                        "_diagnostic": provider_error_diagnostic(
                            provider="whatsapp",
                            status_code=401,
                            body={"message": "API key is not configured"},
                        ),
                    }

                payload = {
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": recipient,
                    "type": "text",
                    "text": {"body": text, "preview_url": False},
                }
                try:
                    operational_event(
                        RuntimeEvent.MESSAGE_STARTED, provider="whatsapp", status="started"
                    )
                    async with httpx.AsyncClient(timeout=10) as client:
                        resp = await client.post(
                            f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages",
                            json=payload,
                            headers={"Authorization": f"Bearer {access_token}"},
                        )
                        if resp.status_code >= 400:
                            operational_event(
                                RuntimeEvent.MESSAGE_FAILED,
                                level="ERROR",
                                provider="whatsapp",
                                http_status=resp.status_code,
                            )
                            return {
                                "status": "error",
                                "error": f"WhatsApp API returned HTTP {resp.status_code}",
                                "_diagnostic": provider_error_diagnostic(
                                    provider="whatsapp",
                                    status_code=resp.status_code,
                                    body=_provider_body(resp),
                                    request_id=resp.headers.get("x-request-id")
                                    or resp.headers.get("request-id"),
                                    retry_after_seconds=_retry_after(
                                        resp.headers.get("retry-after")
                                    ),
                                ),
                            }
                        data = resp.json()
                        msg_id = (data.get("messages") or [{}])[0].get("id", "unknown")
                        operational_event(
                            RuntimeEvent.MESSAGE_ACCEPTED, provider="whatsapp", status="accepted"
                        )
                        return {
                            "status": "ok",
                            "message_id": msg_id,
                            "_connection_id": connection_id,
                            "_provider_message_id": msg_id,
                        }
                except Exception as exc:
                    operational_event(
                        RuntimeEvent.MESSAGE_FAILED,
                        level="ERROR",
                        provider="whatsapp",
                        error_category=error_category(exc),
                    )
                    return {
                        "status": "error",
                        "error": "WhatsApp request failed",
                        "_diagnostic": exception_diagnostic(
                            exc,
                            source="provider",
                            category="provider_request_failed",
                            code="whatsapp_request_failed",
                            message="WhatsApp provider request failed",
                            retryable=True,
                        ),
                    }

            if name.startswith("whatsapp_template_"):
                tool_definition = (
                    self._snapshot.get("_resolved", {})
                    .get("tools", {})
                    .get(name, {})
                    .get("definition", {})
                )
                whatsapp_config = tool_definition.get("whatsapp")
                if not isinstance(whatsapp_config, dict):
                    return {
                        "status": "error",
                        "error": "WhatsApp template tool is missing account configuration",
                        "_diagnostic": exception_diagnostic(
                            ValueError("missing WhatsApp template configuration"),
                            source="runtime",
                            category="tool_configuration",
                            code="whatsapp_tool_unconfigured",
                            message="WhatsApp template tool is not configured",
                            retryable=False,
                        ),
                    }
                (
                    access_token,
                    phone_number_id,
                    connection_id,
                    api_version,
                ) = await self._whatsapp_runtime_config(
                    connection_id=whatsapp_config.get("connection_id"),
                )
                if not access_token or not phone_number_id:
                    operational_event(
                        RuntimeEvent.CREDENTIALS_MISSING, level="WARNING", provider="whatsapp"
                    )
                    return {
                        "status": "error",
                        "error": "WhatsApp credentials not configured on runtime",
                        "_diagnostic": provider_error_diagnostic(
                            provider="whatsapp",
                            status_code=401,
                            body={"message": "API key is not configured"},
                        ),
                    }
                contact = (
                    self._snapshot.get("_resolved", {}).get("contact")
                    or self._snapshot.get("contact_snapshot")
                    or {}
                )
                raw_phone = (
                    (None if self._snapshot.get("_text_test") else args.get("to"))
                    or contact.get("phone_number")
                    or contact.get("phone_e164")
                    or self._snapshot.get("target_snapshot", "")
                )
                recipient = re.sub(r"[^\d]", "", raw_phone)
                if not recipient:
                    operational_event(RuntimeEvent.RECIPIENT_MISSING, level="WARNING")
                    return {"status": "error", "error": "No valid phone number for contact"}

                caller_name = (args.get("caller_name") or contact.get("name") or "there").strip()
                template_name = str(whatsapp_config.get("template_name") or "").strip()
                if not template_name:
                    return {
                        "status": "error",
                        "error": "WhatsApp template name is not configured",
                        "_diagnostic": exception_diagnostic(
                            ValueError("missing WhatsApp template name"),
                            source="runtime",
                            category="tool_configuration",
                            code="whatsapp_template_unconfigured",
                            message="WhatsApp template name is not configured",
                            retryable=False,
                        ),
                    }
                header = whatsapp_config.get("header")
                try:
                    payload = build_whatsapp_template_payload(
                        destination=recipient,
                        template_name=template_name,
                        language=str(whatsapp_config.get("language") or "en"),
                        header=header,
                        parameter_mappings=whatsapp_config.get("parameter_mappings") or {},
                        arguments=args,
                        caller_name=caller_name,
                    )
                except (TypeError, ValueError):
                    return {
                        "status": "error",
                        "error": "WhatsApp template configuration is invalid",
                        "_diagnostic": exception_diagnostic(
                            ValueError("invalid WhatsApp template configuration"),
                            source="runtime",
                            category="tool_configuration",
                            code="whatsapp_template_invalid",
                            message="WhatsApp template configuration is invalid",
                            retryable=False,
                        ),
                    }

                try:
                    operational_event(
                        RuntimeEvent.MESSAGE_STARTED, provider="whatsapp", status="started"
                    )
                    async with httpx.AsyncClient(timeout=10) as client:
                        resp = await client.post(
                            f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages",
                            json=payload,
                            headers={"Authorization": f"Bearer {access_token}"},
                        )
                        if resp.status_code >= 400:
                            operational_event(
                                RuntimeEvent.MESSAGE_FAILED,
                                level="ERROR",
                                provider="whatsapp",
                                http_status=resp.status_code,
                            )
                            return {
                                "status": "error",
                                "error": f"WhatsApp API returned HTTP {resp.status_code}",
                                "_diagnostic": provider_error_diagnostic(
                                    provider="whatsapp",
                                    status_code=resp.status_code,
                                    body=_provider_body(resp),
                                    request_id=resp.headers.get("x-request-id")
                                    or resp.headers.get("request-id"),
                                    retry_after_seconds=_retry_after(
                                        resp.headers.get("retry-after")
                                    ),
                                ),
                            }
                        data = resp.json()
                        msg_id = (data.get("messages") or [{}])[0].get("id", "unknown")
                        operational_event(
                            RuntimeEvent.MESSAGE_ACCEPTED, provider="whatsapp", status="accepted"
                        )
                        result = {
                            "status": "ok",
                            "message_id": msg_id,
                            "_connection_id": connection_id,
                            "_provider_message_id": msg_id,
                        }
                        if isinstance(header, dict):
                            result["media_id"] = header["media_id"]
                        return result
                except Exception as exc:
                    operational_event(
                        RuntimeEvent.MESSAGE_FAILED,
                        level="ERROR",
                        provider="whatsapp",
                        error_category=error_category(exc),
                    )
                    return {
                        "status": "error",
                        "error": "WhatsApp request failed",
                        "_diagnostic": exception_diagnostic(
                            exc,
                            source="provider",
                            category="provider_request_failed",
                            code="whatsapp_request_failed",
                            message="WhatsApp provider request failed",
                            retryable=True,
                        ),
                    }

            if name in ("check_callback_availability", "book_callback"):
                payload = {
                    "run_id": self.run_id,
                }
                if name == "check_callback_availability":
                    payload.update(
                        {"timeframe": args.get("timeframe", ""), "role": args.get("role", "")}
                    )
                else:
                    payload.update(
                        {
                            "slot_id": args.get("slot_id", ""),
                            "reason": args.get("reason", "Customer requested callback"),
                        }
                    )
                try:
                    from voice_api.services.local_runtime_service import local_callback

                    return await local_callback(name, self.run_id, payload)
                except Exception as exc:
                    operational_event(
                        RuntimeEvent.CALLBACK_FAILED,
                        level="ERROR",
                        error_category=error_category(exc),
                    )
                    return {"status": "error", "error": "Callback scheduling service unavailable"}
            if name == "schedule_callback":
                raw_time = (
                    args.get("time") or args.get("when") or args.get("due_at") or args.get("phrase")
                )
                if not isinstance(raw_time, str) or not raw_time.strip():
                    return {"status": "error", "error": "A callback date and time are required"}
                reason = args.get("reason") or "Customer requested callback"
                contact = (
                    self._snapshot.get("_resolved", {}).get("contact")
                    or self._snapshot.get("contact_snapshot")
                    or {}
                )
                contact_id = contact.get("id") or self._snapshot.get("contact_id")
                agent_version_id = self._snapshot.get("agent_version_id") or (
                    self._snapshot.get("_resolved", {}).get("agent_version") or {}
                ).get("id")
                if not contact_id or not agent_version_id:
                    operational_event(RuntimeEvent.CALLBACK_INVALID, level="WARNING")
                    return {
                        "status": "error",
                        "error": "Contact ID or Agent Version ID not found in session",
                    }

                timezone = args.get("timezone") or contact.get("timezone")
                if not isinstance(timezone, str) or not timezone.strip():
                    return {
                        "status": "error",
                        "error": "The contact timezone is unknown; ask for it before scheduling",
                    }

                try:
                    from uuid import uuid4

                    from voice_api.db.session import SessionFactory
                    from voice_api.db.tenant_scope import bind_run_organization
                    from voice_api.models import Callback
                    from voice_api.services.calendar_service import (
                        SchedulingError,
                        format_local_callback_time,
                        resolve_timeframe,
                    )

                    try:
                        due_at = resolve_timeframe(raw_time, timezone).start
                    except SchedulingError:
                        return {"status": "error", "error": "Callback time could not be resolved"}
                    formatted_time = format_local_callback_time(due_at, timezone)
                    request_key = f"{self.run_id}_{uuid4().hex[:8]}"
                    async with SessionFactory() as session:
                        await bind_run_organization(session, self.run_id)
                        cb = Callback(
                            request_key=request_key,
                            contact_id=contact_id,
                            agent_version_id=agent_version_id,
                            due_at=due_at,
                            timezone=timezone,
                            original_phrase=raw_time.strip(),
                            status="scheduled",
                            reason=reason,
                        )
                        session.add(cb)
                        await session.commit()
                        operational_event(
                            RuntimeEvent.CALLBACK_CREATED,
                            status="completed",
                            run_id=opaque_id(self.run_id),
                            callback_id=opaque_id(cb.id),
                        )
                        return {
                            "status": "ok",
                            "callback_id": cb.id,
                            "scheduled_time": formatted_time,
                            "message": f"Callback request recorded for {formatted_time}.",
                        }
                except Exception as exc:
                    operational_event(
                        RuntimeEvent.CALLBACK_FAILED,
                        level="ERROR",
                        error_category=error_category(exc),
                    )
                    return {"status": "error", "error": "Failed to persist callback"}

            definition = (
                self._snapshot.get("_resolved", {})
                .get("tools", {})
                .get(name, {})
                .get("definition", {})
            )
            if definition.get("handler") == "query_knowledge_base":
                query_text = (
                    args.get("query")
                    or args.get("question")
                    or args.get("search")
                    or args.get("topic")
                    or ""
                ).strip()
                if not query_text:
                    return {"status": "error", "error": "Missing search query parameter"}

                kb_id = definition.get("knowledge_base_id")
                attached_ids = {
                    kb["id"]
                    for kb in self._snapshot.get("_resolved", {}).get("knowledge", [])
                    if kb.get("id")
                }
                if not kb_id or kb_id not in attached_ids:
                    return {
                        "status": "error",
                        "error": "Knowledge tool is not scoped to an attached knowledge base",
                    }

                all_hits = []
                try:
                    from voice_runtime.contracts.knowledge import RetrievalConfig

                    from voice_api.db.session import SessionFactory
                    from voice_api.db.tenant_scope import bind_run_organization
                    from voice_api.knowledge.embeddings import GeminiEmbedder
                    from voice_api.services.knowledge_service import search

                    gemini_key = stage_api_key(self.settings, "embedding", "gemini") or ""
                    retrieval_cfg = RetrievalConfig.model_validate(
                        self._snapshot.get("retrieval", {})
                    )

                    async with SessionFactory() as db_session, httpx.AsyncClient() as http_client:
                        await bind_run_organization(db_session, self.run_id)
                        embedder = GeminiEmbedder(gemini_key, http_client) if gemini_key else None
                        hits = await search(db_session, kb_id, query_text, retrieval_cfg, embedder)
                        all_hits.extend(hits)
                except Exception as exc:
                    operational_event(
                        RuntimeEvent.RETRIEVAL_FAILED,
                        level="ERROR",
                        error_category=error_category(exc),
                    )
                    return {"status": "error", "error": "Knowledge search failed"}

                all_hits.sort(key=lambda h: h.score, reverse=True)
                top_hits = all_hits[:5]
                if not top_hits:
                    return {
                        "status": "not_found",
                        "hits": [],
                        "context": "No relevant information found in knowledge base.",
                    }

                context_excerpts = "\n\n".join(
                    f"[{h.title}; chunk {h.chunk_id}]\n{h.content[:600]}" for h in top_hits[:3]
                )
                return {
                    "status": "ok",
                    "knowledge_base_id": kb_id,
                    "hits_count": len(all_hits),
                    "context": context_excerpts,
                    "results": [
                        {
                            "chunk_id": h.chunk_id,
                            "title": h.title,
                            "source_path": h.source_path,
                            "score": round(h.score, 4),
                        }
                        for h in top_hits[:3]
                    ],
                }

            return {"status": "error", "error": "Tool adapter is not connected to live runtime"}

        return execute
