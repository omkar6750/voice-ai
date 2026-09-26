"""Service for managing browser-based WebRTC voice sessions."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import httpx
from fastapi import HTTPException
from loguru import logger
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection
from pipecat.transports.smallwebrtc.request_handler import (
    IceCandidate,
    SmallWebRTCPatchRequest,
    SmallWebRTCRequest,
    SmallWebRTCRequestHandler,
)
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from voice_runtime.execution.delivery import stream_evidence
from voice_runtime.execution.evidence_client import ApiEvidenceIngestor
from voice_runtime.execution.exchange import ExchangeTracker
from voice_runtime.execution.native import NativePipelineHost
from voice_runtime.execution.spool import DurableSpool

from voice_api.core.config import Settings
from voice_api.db.session import SessionFactory
from voice_api.models import AgentVersion, BrowserSession, Contact, Run
from voice_api.models.common import new_id, now
from voice_api.schemas.browser_session import WebRTCOfferRequest, WebRTCPatchRequest
from voice_api.services.resolution_service import fingerprint, resolve


class BrowserSessionContext:
    def __init__(self, session_id: str, run_id: str, snapshot: dict) -> None:
        self.session_id = session_id
        self.run_id = run_id
        self.snapshot = snapshot
        self.request_handler = SmallWebRTCRequestHandler()
        self.host: NativePipelineHost | None = None
        self.pipeline_task: asyncio.Task | None = None
        self.is_active = True
        self.has_connected = False
        self.connection_id: str | None = None
        self.connected_event = asyncio.Event()

    def mark_ended(self) -> None:
        self.is_active = False

    async def is_still_active(self) -> bool:
        return self.is_active


class BrowserSessionManager:
    def __init__(self) -> None:
        self._sessions: dict[str, BrowserSessionContext] = {}
        self._lock = asyncio.Lock()

    async def get_or_create_context(
        self, session_id: str, run_id: str, snapshot: dict
    ) -> BrowserSessionContext:
        async with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = BrowserSessionContext(session_id, run_id, snapshot)
            return self._sessions[session_id]

    def get_context(self, session_id: str) -> BrowserSessionContext | None:
        return self._sessions.get(session_id)

    async def remove_context(self, session_id: str) -> None:
        async with self._lock:
            self._sessions.pop(session_id, None)


browser_session_manager = BrowserSessionManager()


async def create_browser_session(
    session: AsyncSession,
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
    else:
        stmt = (
            select(AgentVersion)
            .where(AgentVersion.status == "published")
            .order_by(AgentVersion.version.desc())
        )
        version = await session.scalar(stmt)
        if version is None:
            stmt = select(AgentVersion).order_by(AgentVersion.version.desc())
            version = await session.scalar(stmt)
        if version is None:
            raise HTTPException(400, "No agent version found to test")

    resolved_contact_id: str | None = None
    contact_snapshot: dict[str, Any] = {}

    if contact_id:
        contact = await session.get(Contact, contact_id)
        if contact is None:
            raise HTTPException(404, "Contact not found")
        resolved_contact_id = contact.id
        effective_phone = (
            phone_number.strip()
            if phone_number and phone_number.strip()
            else contact.phone_number
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


async def handle_browser_offer(
    session_id: str,
    body: WebRTCOfferRequest,
    settings: Settings,
    session: AsyncSession,
) -> dict[str, Any]:
    """Handle WebRTC offer from browser, setting up SmallWebRTC and NativePipelineHost."""
    browser_session = await session.get(BrowserSession, session_id)
    if not browser_session:
        raise HTTPException(404, "Browser session not found")

    if browser_session.status in ("disconnected", "expired", "failed"):
        raise HTTPException(410, "Browser session is no longer active")

    run = await session.get(Run, browser_session.run_id)
    if not run:
        raise HTTPException(404, "Run not found for browser session")

    ctx = await browser_session_manager.get_or_create_context(
        session_id=session_id,
        run_id=run.id,
        snapshot=run.resolved_config,
    )

    if ctx.has_connected or browser_session.status == "connected":
        raise HTTPException(409, "Browser session is already connected")

    async def on_webrtc_connection(pipecat_connection: SmallWebRTCConnection) -> None:
        if ctx.has_connected:
            logger.warning("Duplicate connection attempted for browser session {}", session_id)
            raise HTTPException(409, "Duplicate connection not allowed")

        ctx.has_connected = True
        ctx.connection_id = pipecat_connection.pc_id
        ctx.connected_event.set()

        async with SessionFactory() as db_session:
            bs = await db_session.get(BrowserSession, session_id)
            if bs:
                bs.status = "connected"
                bs.connected_at = now()
                bs.connection_id = pipecat_connection.pc_id
            r = await db_session.get(Run, run.id)
            if r:
                r.status = "running"
                r.started_at = now()
            await db_session.commit()

        transport = SmallWebRTCTransport(
            webrtc_connection=pipecat_connection,
            params=TransportParams(
                audio_in_enabled=True,
                audio_out_enabled=True,
            ),
        )

        @transport.event_handler("on_client_disconnected")
        async def on_client_disconnected(_transport, _client):
            logger.info("Browser WebRTC client disconnected for session {}", session_id)
            ctx.mark_ended()

        ctx.pipeline_task = asyncio.create_task(_run_browser_pipeline(ctx, transport, settings))

    req = SmallWebRTCRequest(
        sdp=body.sdp,
        type=body.type,
        pc_id=body.pc_id,
        restart_pc=body.restart_pc,
        request_data=body.request_data,
    )

    answer = await ctx.request_handler.handle_web_request(req, on_webrtc_connection)
    if answer is None:
        raise HTTPException(500, "Failed to generate WebRTC SDP answer")

    return answer


async def handle_browser_patch(
    session_id: str,
    body: WebRTCPatchRequest,
) -> dict[str, str]:
    """Apply ICE candidate patches for the session's WebRTC peer connection."""
    ctx = browser_session_manager.get_context(session_id)
    if not ctx:
        raise HTTPException(404, "Active browser session not found")

    candidates = [
        IceCandidate(
            candidate=c.candidate,
            sdp_mid=c.sdp_mid,
            sdp_mline_index=c.sdp_mline_index,
        )
        for c in body.candidates
    ]
    patch_req = SmallWebRTCPatchRequest(pc_id=body.pc_id, candidates=candidates)
    await ctx.request_handler.handle_patch_request(patch_req)
    return {"status": "ok"}


async def end_browser_session(session_id: str, session: AsyncSession) -> dict[str, str]:
    """End an active browser session, cleaning up worker, host, and run status."""
    browser_session = await session.get(BrowserSession, session_id)
    if not browser_session:
        raise HTTPException(404, "Browser session not found")

    ctx = browser_session_manager.get_context(session_id)
    if ctx:
        ctx.mark_ended()
        if ctx.host:
            await ctx.host.close()
        if ctx.request_handler:
            await ctx.request_handler.close()
        if ctx.pipeline_task and not ctx.pipeline_task.done():
            ctx.pipeline_task.cancel()
        await browser_session_manager.remove_context(session_id)

    browser_session.status = "disconnected"
    if not browser_session.disconnected_at:
        browser_session.disconnected_at = now()

    run = await session.get(Run, browser_session.run_id)
    if run and run.status in ("claimed", "running"):
        run.status = "completed"
        if not run.ended_at:
            run.ended_at = now()

    await session.commit()
    return {"status": "disconnected"}


async def _run_browser_pipeline(
    ctx: BrowserSessionContext,
    transport: SmallWebRTCTransport,
    settings: Settings,
) -> None:
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
            settings.sarvam_api_key,
            settings.cartesia_api_key,
            settings.gemini_api_key,
        )
        if s
    )
    tracker = ExchangeTracker(run_id, spool, secrets=(*secrets, settings.operator_token or ""))

    from voice_api.main import app

    headers = {"Authorization": f"Bearer {settings.operator_token}"}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://runtime.local"
    ) as client:
        ingestor = ApiEvidenceIngestor(client, run_id, settings.operator_token or "")
        delivery_task = asyncio.create_task(stream_evidence(spool, ingestor))

        try:
            await host.prepare(snapshot, tracker, transport=transport)
            await host.converse(ctx.is_still_active)
        except Exception as exc:
            logger.exception("Browser pipeline failed during run {}: {}", run_id, exc)
            async with SessionFactory() as db_session:
                r = await db_session.get(Run, run_id)
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
            await host.close()
            delivery_task.cancel()

            async with SessionFactory() as db_session:
                r = await db_session.get(Run, run_id)
                if r and r.status in ("claimed", "running"):
                    r.status = "completed"
                    if not r.ended_at:
                        r.ended_at = now()
                bs = await db_session.get(BrowserSession, session_id)
                if bs and bs.status in ("created", "connecting", "connected"):
                    bs.status = "disconnected"
                    if not bs.disconnected_at:
                        bs.disconnected_at = now()
                await db_session.commit()

            if host.directory.exists():
                for kind in ("input", "output", "mixed", "pipeline_log"):
                    filename = "pipeline.log" if kind == "pipeline_log" else f"{kind}.wav"
                    if not (host.directory / filename).is_file():
                        continue
                    try:
                        await client.post(
                            f"/api/runs/{run_id}/artifacts",
                            headers=headers,
                            json={
                                "id": str(uuid5(NAMESPACE_URL, f"{run_id}/{kind}")),
                                "kind": kind,
                                "path": f"{run_id}/{filename}",
                            },
                        )
                    except Exception:
                        pass
