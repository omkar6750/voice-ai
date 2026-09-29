"""Service for managing browser-based voice sessions."""

from __future__ import annotations

import asyncio
import hashlib
import secrets
import time
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

from fastapi import HTTPException, WebSocket
from loguru import logger
from pipecat.serializers.protobuf import ProtobufFrameSerializer
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams, FastAPIWebsocketTransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from voice_runtime.diagnostics import text_error_diagnostic
from voice_runtime.execution.delivery import stream_evidence
from voice_runtime.execution.exchange import ExchangeTracker
from voice_runtime.execution.native import NativePipelineHost
from voice_runtime.execution.spool import DurableSpool

from voice_api.core.config import Settings
from voice_api.db.session import SessionFactory
from voice_api.db.tenant_scope import bind_organization
from voice_api.models import Agent, AgentVersion, BrowserSession, Contact, Run
from voice_api.models.common import new_id, now
from voice_api.schemas.diagnostics import DiagnosticInput
from voice_api.services.diagnostic_service import persist_diagnostic
from voice_api.services.local_runtime_service import LocalEvidenceIngestor, register_local_artifacts
from voice_api.services.provider_credentials import settings_for_organization
from voice_api.services.resolution_service import fingerprint, resolve


class BrowserSessionContext:
    def __init__(self, session_id: str, run_id: str, snapshot: dict, org_id: str) -> None:
        self.session_id = session_id
        self.run_id = run_id
        self.snapshot = snapshot
        self.org_id = org_id
        self.host: NativePipelineHost | None = None
        self.pipeline_task: asyncio.Task | None = None
        self.is_active = True
        self.has_connected = False
        self.connection_id: str | None = None
        self.ticket_hash: str | None = None
        self.ticket_expires_at = 0.0
        self.cleanup_lock = asyncio.Lock()
        self.cleanup_complete = False
        self.disconnect_reason = "browser_disconnect"

    def mark_ended(self) -> None:
        self.is_active = False

    async def is_still_active(self) -> bool:
        return self.is_active

    async def close_runtime(self) -> None:
        """Close runtime resources exactly once, without cancelling the caller task."""
        current = asyncio.current_task()
        if self.pipeline_task is current:
            self.mark_ended()
            await self._close_resources()
            self.cleanup_complete = True
            return
        async with self.cleanup_lock:
            if self.cleanup_complete:
                return
            self.mark_ended()
            if self.pipeline_task:
                if not self.pipeline_task.done():
                    self.pipeline_task.cancel()
                await asyncio.gather(self.pipeline_task, return_exceptions=True)
                if self.cleanup_complete:
                    return
            await self._close_resources()
            self.cleanup_complete = True

    async def _close_resources(self) -> None:
        if self.host:
            await self.host.close()


class BrowserSessionManager:
    def __init__(self) -> None:
        self._sessions: dict[str, BrowserSessionContext] = {}
        self._lock = asyncio.Lock()

    def get_context(self, session_id: str) -> BrowserSessionContext | None:
        return self._sessions.get(session_id)

    async def remove_context(self, session_id: str) -> None:
        async with self._lock:
            self._sessions.pop(session_id, None)

    async def issue_ticket(self, session_id: str, run_id: str, snapshot: dict, org_id: str) -> str:
        async with self._lock:
            now_mono = time.monotonic()
            for other_id, other in list(self._sessions.items()):
                if other_id == session_id:
                    continue
                if other.is_active and (other.has_connected or other.ticket_expires_at > now_mono):
                    raise HTTPException(409, "Another browser call is active")
                if not other.has_connected and other.ticket_expires_at <= now_mono:
                    self._sessions.pop(other_id, None)
            ctx = self._sessions.setdefault(
                session_id, BrowserSessionContext(session_id, run_id, snapshot, org_id)
            )
            if ctx.has_connected or not ctx.is_active:
                raise HTTPException(409, "Browser session is already connected")
            ticket = secrets.token_urlsafe(32)
            ctx.ticket_hash = hashlib.sha256(ticket.encode()).hexdigest()
            ctx.ticket_expires_at = now_mono + 30
            return ticket

    async def consume_ticket(self, session_id: str, ticket: str) -> BrowserSessionContext | None:
        async with self._lock:
            ctx = self._sessions.get(session_id)
            if not ctx or not ctx.ticket_hash or ctx.has_connected or not ctx.is_active:
                return None
            if time.monotonic() >= ctx.ticket_expires_at:
                ctx.ticket_hash = None
                return None
            if not secrets.compare_digest(
                ctx.ticket_hash, hashlib.sha256(ticket.encode()).hexdigest()
            ):
                return None
            ctx.ticket_hash = None
            ctx.ticket_expires_at = 0.0
            ctx.has_connected = True
            return ctx


browser_session_manager = BrowserSessionManager()


async def create_browser_session(
    session: AsyncSession,
    agent_id: str | None = None,
    agent_version_id: str | None = None,
    contact_id: str | None = None,
    phone_number: str | None = None,
    contact_variables: dict[str, Any] | None = None,
    logging_override: bool | None = None,
) -> tuple[Run, BrowserSession]:
    """Create a Run and associated BrowserSession for in-browser testing."""
    if agent_version_id:
        version = await session.get(AgentVersion, agent_version_id)
        if version is None:
            raise HTTPException(404, "Agent version not found")
        if agent_id and version.agent_id != agent_id:
            raise HTTPException(422, "Agent version does not belong to the selected agent")
    else:
        if not agent_id:
            raise HTTPException(422, "Select an agent before starting a browser test")
        agent = await session.get(Agent, agent_id)
        if agent is None:
            raise HTTPException(404, "Agent not found")
        version = None
        if agent.active_version_id:
            active = await session.get(AgentVersion, agent.active_version_id)
            if active is not None and active.status == "published":
                version = active
        if version is None:
            version = await session.scalar(
                select(AgentVersion)
                .where(
                    AgentVersion.agent_id == agent_id,
                    AgentVersion.status == "published",
                )
                .order_by(AgentVersion.version.desc())
            )
        if version is None:
            raise HTTPException(422, "Selected agent has no published version to test")

    resolved_contact_id: str | None = None
    contact_snapshot: dict[str, Any] = {}

    if contact_id:
        contact = await session.get(Contact, contact_id)
        if contact is None:
            raise HTTPException(404, "Contact not found")
        resolved_contact_id = contact.id
        effective_phone = (
            phone_number.strip() if phone_number and phone_number.strip() else contact.phone_number
        )
        contact_snapshot = {
            "id": contact.id,
            "name": contact.name,
            "timezone": contact.timezone or "UTC",
            "phone_number": effective_phone,
            "business": contact.business,
            "source": contact.source,
            "language": contact.language or "en",
            "metadata_json": dict(contact.metadata_json or {}),
        }
        if contact_variables:
            for k, v in contact_variables.items():
                contact_snapshot["metadata_json"][k] = v
                if k in ("name", "business", "source", "timezone", "language") and v:
                    contact_snapshot[k] = v
    elif (phone_number and phone_number.strip()) or contact_variables:
        clean_phone = (phone_number or "").strip()
        custom_vars = dict(contact_variables or {})
        synth_name = custom_vars.get("name") or "Test Caller"
        synth_id = f"test-contact-{new_id()[:8]}"
        contact_snapshot = {
            "id": synth_id,
            "name": synth_name,
            "timezone": custom_vars.get("timezone", "UTC"),
            "phone_number": clean_phone,
            "business": custom_vars.get("business"),
            "source": custom_vars.get("source", "browser_test"),
            "language": custom_vars.get("language", "en"),
            "metadata_json": custom_vars,
        }

    config, digest = await resolve(session, version, logging_override)

    snapshot = dict(config)
    resolved_dict = dict(snapshot.get("_resolved", {}))
    if contact_snapshot:
        resolved_dict["contact"] = contact_snapshot
        snapshot["contact_snapshot"] = contact_snapshot
        snapshot["target_snapshot"] = contact_snapshot.get("phone_number", "")
        snapshot["contact_id"] = resolved_contact_id or contact_snapshot.get("id")
    snapshot["agent_version_id"] = version.id
    snapshot["_resolved"] = resolved_dict
    digest = fingerprint(snapshot)

    run = Run(
        id=new_id(),
        channel="browser",
        transport_provider="dashboard",
        agent_version_id=version.id,
        contact_id=resolved_contact_id,
        endpoint_id=None,
        status="claimed",
        resolved_config=snapshot,
        config_hash=digest,
        snapshot_schema_version=1,
        contact_snapshot=contact_snapshot,
    )
    session.add(run)
    await session.flush()

    browser_session = BrowserSession(
        id=new_id(),
        run_id=run.id,
        status="created",
        expires_at=now() + timedelta(minutes=5),
    )
    session.add(browser_session)
    await session.commit()

    return run, browser_session


async def issue_browser_ticket(session_id: str, session: AsyncSession) -> dict[str, Any]:
    browser_session = await session.get(BrowserSession, session_id)
    if not browser_session:
        raise HTTPException(404, "Browser session not found")

    if browser_session.status != "created" or (
        browser_session.expires_at and browser_session.expires_at <= now()
    ):
        raise HTTPException(410, "Browser session is no longer active")

    run = await session.get(Run, browser_session.run_id)
    if not run:
        raise HTTPException(404, "Run not found for browser session")

    if not browser_session.org_id or run.org_id != browser_session.org_id:
        raise HTTPException(404, "Browser session not found")
    ticket = await browser_session_manager.issue_ticket(
        session_id, run.id, run.resolved_config, browser_session.org_id
    )
    return {"ticket": ticket}


async def handle_browser_socket(session_id: str, websocket: WebSocket, settings: Settings) -> None:
    origin = websocket.headers.get("origin")
    allowed = [s.strip() for s in settings.clerk_authorized_parties.split(",") if s.strip()]
    if not origin or origin not in allowed:
        await websocket.close(code=1008)
        return
    ticket = websocket.query_params.get("ticket", "")
    ctx = await browser_session_manager.consume_ticket(session_id, ticket)
    if not ctx:
        await websocket.close(code=1008)
        return
    try:
        async with SessionFactory() as db_session:
            bind_organization(db_session.sync_session, ctx.org_id)
            bs = await db_session.get(BrowserSession, session_id)
            run = await db_session.get(Run, ctx.run_id)
            if not bs or bs.status != "created" or not run or bs.run_id != run.id:
                await websocket.close(code=1008)
                return
            ctx.connection_id = str(uuid4())
            bs.status = "connected"
            bs.connected_at = now()
            bs.connection_id = ctx.connection_id
            run.status = "running"
            run.started_at = now()
            await db_session.commit()
        await websocket.accept()
        transport = FastAPIWebsocketTransport(
            websocket=websocket,
            params=FastAPIWebsocketParams(
                audio_in_enabled=True,
                audio_out_enabled=True,
                add_wav_header=False,
                serializer=ProtobufFrameSerializer(),
                session_timeout=300,
                allowed_origins=allowed,
            ),
        )

        @transport.event_handler("on_client_disconnected")
        async def on_client_disconnected(_transport, _client):
            ctx.mark_ended()

        @transport.event_handler("on_session_timeout")
        async def on_session_timeout(_transport, _client):
            ctx.disconnect_reason = "browser_timeout"
            ctx.mark_ended()

        ctx.pipeline_task = asyncio.create_task(_run_browser_pipeline(ctx, transport, settings))
        await ctx.pipeline_task
    finally:
        ctx.mark_ended()
        await browser_session_manager.remove_context(session_id)


async def end_browser_session(
    session_id: str, session: AsyncSession, *, reason: str = "operator_stop"
) -> dict[str, str]:
    """End an active browser session, cleaning up worker, host, and run status."""
    browser_session = await session.get(BrowserSession, session_id)
    if not browser_session:
        raise HTTPException(404, "Browser session not found")

    ctx = browser_session_manager.get_context(session_id)
    if ctx:
        ctx.disconnect_reason = "operator_stop"
        await ctx.close_runtime()
        await browser_session_manager.remove_context(session_id)

    browser_session.status = "disconnected"
    if not browser_session.disconnected_at:
        browser_session.disconnected_at = now()

    run = await session.get(Run, browser_session.run_id)
    if run and run.status in ("claimed", "running"):
        await persist_diagnostic(
            session,
            run.id,
            DiagnosticInput(
                diagnostic_id=str(uuid5(NAMESPACE_URL, f"{run.id}/browser/{reason}")),
                occurred_at=now(),
                severity="info" if reason == "operator_stop" else "warning",
                category="call_termination",
                source="transport",
                code=(
                    "browser_operator_stop" if reason == "operator_stop" else "browser_disconnect"
                ),
                message=(
                    "Browser call ended by operator"
                    if reason == "operator_stop"
                    else "Browser connection ended unexpectedly"
                ),
                uncertain=reason != "operator_stop",
            ),
        )
        run.status = "completed"
        if not run.ended_at:
            run.ended_at = now()

    await session.commit()
    return {"status": "disconnected"}


async def _run_browser_pipeline(
    ctx: BrowserSessionContext,
    transport: FastAPIWebsocketTransport,
    settings: Settings,
) -> None:
    async with SessionFactory() as credential_session:
        settings = await settings_for_organization(credential_session, ctx.org_id, settings)
    run_id = ctx.run_id
    session_id = ctx.session_id
    snapshot = ctx.snapshot
    recordings_dir = Path(settings.recordings_dir)
    host = NativePipelineHost(
        run_id=run_id,
        recordings_dir=recordings_dir,
        settings=settings,
    )
    ctx.host = host

    spool_path = Path("data/evidence") / f"{run_id}.jsonl"
    spool_path.parent.mkdir(parents=True, exist_ok=True)
    spool = DurableSpool(spool_path)
    secrets = tuple(
        s
        for s in (
            settings.groq_api_key,
            settings.jev_api_key,
            settings.sarvam_api_key,
            settings.cartesia_api_key,
            settings.gemini_api_key,
        )
        if s
    )
    tracker = ExchangeTracker(run_id, spool, secrets=secrets)
    ingestor = LocalEvidenceIngestor(run_id, org_id=ctx.org_id)
    delivery_task = asyncio.create_task(stream_evidence(spool, ingestor))

    try:
        await host.prepare(snapshot, tracker, transport=transport, enable_rtvi=True)
        await host.converse(ctx.is_still_active)
    except Exception as exc:
        logger.exception("Browser pipeline failed during run {}: {}", run_id, exc)
        async with SessionFactory() as db_session:
            bind_organization(db_session.sync_session, ctx.org_id)
            r = await db_session.get(Run, run_id)
            if r:
                await persist_diagnostic(
                    db_session,
                    run_id,
                    DiagnosticInput.model_validate(text_error_diagnostic(str(exc))),
                )
            if r and r.status not in ("completed", "canceled"):
                r.status = "failed"
                r.error = f"Pipeline execution failed: {exc}"
                r.ended_at = now()
            bs = await db_session.get(BrowserSession, session_id)
            if bs:
                bs.status = "failed"
                bs.disconnected_at = now()
            await db_session.commit()
    finally:
        ctx.mark_ended()
        await ctx.close_runtime()
        delivery_task.cancel()
        await asyncio.gather(delivery_task, return_exceptions=True)

        async with SessionFactory() as db_session:
            bind_organization(db_session.sync_session, ctx.org_id)
            r = await db_session.get(Run, run_id)
            bs = await db_session.get(BrowserSession, session_id)
            if (
                r
                and bs
                and r.status in ("claimed", "running")
                and bs.status in ("created", "connecting", "connected")
                and ctx.disconnect_reason != "operator_stop"
            ):
                await persist_diagnostic(
                    db_session,
                    run_id,
                    DiagnosticInput(
                        diagnostic_id=str(
                            uuid5(NAMESPACE_URL, f"{run_id}/browser/{ctx.disconnect_reason}")
                        ),
                        occurred_at=now(),
                        severity="warning",
                        category="call_termination",
                        source="transport",
                        code=ctx.disconnect_reason,
                        message="Browser voice connection ended",
                        uncertain=True,
                    ),
                )
            if r and r.status in ("claimed", "running"):
                r.status = "completed"
                if not r.ended_at:
                    r.ended_at = now()
            if bs and bs.status in ("created", "connecting", "connected"):
                bs.status = "disconnected"
                if not bs.disconnected_at:
                    bs.disconnected_at = now()
            await db_session.commit()

        await register_local_artifacts(run_id, host.directory, org_id=ctx.org_id)
