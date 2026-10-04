"""Native local / Docker hosted runtime. No database or Clerk dependencies."""

from __future__ import annotations

import asyncio
import hashlib
import secrets
import time
from contextlib import asynccontextmanager
from uuid import uuid4

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from voice_runtime.safe_logs import configure_safe_logging
from voice_shared.contracts import ModemProbe, PrepareSession, SessionIdentity, configuration_hash
from voice_shared.http_clients import install
from voice_shared.logging import HttpLoggingMiddleware, configure, exception_event

from voice_runner.capacity import Capacity
from voice_runner.session import Session
from voice_runner.settings import get_settings

configure_safe_logging()


class Manager:
    def __init__(self, settings):
        self.settings = settings
        self.boot_id = uuid4()
        self.sessions = {}
        self.lock = asyncio.Lock()
        self.capacity = Capacity(settings)
        self.dropped_logs = 0
        self.cleanup_tasks = set()
        self.probe_ports = set()
        self.upload_semaphore = asyncio.Semaphore(2)
        self.capacity.pressure = self.pressure
        self.control_client = httpx.AsyncClient(
            base_url=settings.api_base_url,
            headers={"X-Voice-Runtime-Token": settings.runtime_service_token.get_secret_value()},
            timeout=18,
            limits=httpx.Limits(max_connections=16, max_keepalive_connections=8),
        )
        self.upload_client = httpx.AsyncClient(
            base_url=settings.api_base_url,
            timeout=60,
            limits=httpx.Limits(max_connections=2, max_keepalive_connections=2),
            headers={"X-Voice-Runtime-Token": settings.runtime_service_token.get_secret_value()},
        )

        # Storage origins must never receive API service authentication headers.
        self.storage_client = httpx.AsyncClient(
            timeout=60, limits=httpx.Limits(max_connections=2, max_keepalive_connections=2)
        )

    def pressure(self):
        import shutil
        from pathlib import Path

        spools = [
            s.spool for s in tuple(self.sessions.values()) if s.spool and not s.closed.is_set()
        ]
        captures = [
            getattr(s.host, "capture", None) for s in tuple(self.sessions.values()) if s.host
        ]
        usage = shutil.disk_usage(Path(self.settings.runtime_spool_dir).parent)
        # Admission depends on usable free space, not unrelated disk occupancy.
        disk = min(1.0, self.settings.runtime_min_free_spool_bytes / max(usage.free, 1))
        return {
            "spool_queue_pressure": max(
                (s._queue.qsize() / s._queue.maxsize for s in spools), default=0
            ),
            "spool_disk_pressure": max(
                (
                    Path(s.path).stat().st_size / s.max_bytes
                    for s in spools
                    if Path(s.path).exists()
                ),
                default=0,
            ),
            "disk_pressure": disk,
            "audio_queue_pressure": max(
                (
                    c._writes.qsize() / c._writes.maxsize
                    for c in captures
                    if c and hasattr(c, "_writes")
                ),
                default=0,
            ),
        }

    def metrics(self):
        return {
            **self.capacity.metrics,
            "active_sessions": sum(
                s.state not in {"ended", "uncertain", "prepared"} for s in self.sessions.values()
            ),
            "reserved_sessions": sum(s.state == "prepared" for s in self.sessions.values()),
            "dropped_logs": self.dropped_logs
            + sum(
                getattr(getattr(s, "diagnostic_capture", None), "dropped", 0)
                for s in self.sessions.values()
            ),
        }

    async def prepare(self, request):
        if configuration_hash(request.snapshot) != request.config_hash:
            raise HTTPException(422, "Compiled configuration hash mismatch")
        if request.expires_at <= time.time() or request.expires_at > time.time() + 1800:
            raise HTTPException(422, "Session grant lifetime invalid")
        endpoint = request.snapshot.get("_resolved", {}).get("endpoint", {})
        modem_config = (
            request.channel == "sim7600" or endpoint.get("at_port") or endpoint.get("audio_port")
        )
        if modem_config and not self.settings.local:
            raise HTTPException(404, "SIM7600 unavailable in hosted environments")
        if not self.settings.local and request.channel not in {"browser", "text_test"}:
            raise HTTPException(409, "Hosted runtime supports browser calls and chat tests only")
        if not self.settings.local and not self.settings.hosted_calls_enabled:
            raise HTTPException(503, "Hosted runtime disabled pending acceptance")
        if request.channel == "twilio":
            from urllib.parse import urlsplit

            for value in (request.api_public_base_url, self.settings.runtime_public_base_url):
                parsed = urlsplit(value)
                if (
                    parsed.scheme != "https"
                    or not parsed.hostname
                    or parsed.username
                    or parsed.password
                    or parsed.query
                    or parsed.fragment
                    or parsed.path not in {"", "/"}
                ):
                    raise HTTPException(
                        422, "Twilio requires canonical HTTPS callback and media URLs"
                    )
        async with self.lock:
            existing = self.sessions.get(str(request.run_id))
            if existing:
                if existing.generation != str(request.generation):
                    raise HTTPException(409, "Run already assigned; refusing repeat execution")
                return existing
            count = sum(s.state not in {"ended"} for s in self.sessions.values())
            if not self.capacity.allows(count):
                raise HTTPException(409, "Runtime busy; no call queued")
            if request.channel == "sim7600":
                endpoint = request.snapshot.get("_resolved", {}).get("endpoint", {})
                ports = {str(endpoint.get(k, "")).casefold() for k in ("at_port", "audio_port")}
                if (
                    ports & self.probe_ports
                    or not all(ports)
                    or any(
                        p
                        for s in self.sessions.values()
                        if s.state != "ended" and s.request.channel == "sim7600"
                        for p in ports
                        if p in s.modem_ports
                    )
                ):
                    raise HTTPException(409, "Modem ports unavailable")
            session = Session(self, request)
            self.sessions[session.run_id] = session
            try:
                await session.initialize()
            except Exception:
                self.sessions.pop(session.run_id, None)
                raise
            return session

    def get(self, run_id, generation=None, boot_id=None):
        if boot_id and str(boot_id) != str(self.boot_id):
            raise HTTPException(409, "Stale runtime boot")
        session = self.sessions.get(str(run_id))
        if not session or (generation and session.generation != str(generation)):
            raise HTTPException(404, "Assigned session unavailable")
        return session

    async def start(self, session):
        async with self.lock:
            if session.state != "prepared":
                return {"state": session.state, "provider_call_id": session.call_sid}
            session.state = "starting"
            session.lease_until = time.monotonic() + 30
            if session.request.channel == "sim7600":
                session.task = asyncio.create_task(
                    session.run_pipeline(), name=f"sim-{session.run_id}"
                )
            elif session.request.channel == "twilio":
                session.task = asyncio.create_task(
                    self.dial(session), name=f"dial-{session.run_id}"
                )
            else:
                session.state = "waiting_media"
        return {"state": session.state, "provider_call_id": session.call_sid}

    async def dial(self, session):
        from voice_runtime.telephony.twilio import (
            PublicTelephonyUrls,
            TwilioCallController,
            TwilioCredentials,
        )

        creds = TwilioCredentials(
            **{k: v.get_secret_value() for k, v in session.request.telephony_credentials.items()}
        )
        api_urls = PublicTelephonyUrls(session.request.api_public_base_url)
        runtime_urls = PublicTelephonyUrls(self.settings.runtime_public_base_url)
        try:
            controller = TwilioCallController(creds)
            session.call_sid = await controller.dial(
                to=session.request.destination,
                from_number=session.request.from_number,
                media_ws_url=runtime_urls.twilio_media(session.request.correlation_id),
                status_callback_url=api_urls.twilio_call_status(session.request.correlation_id),
                stream_status_callback_url=api_urls.twilio_stream_status(
                    session.request.correlation_id
                ),
                correlation_id=session.request.correlation_id,
                run_id=session.run_id,
            )
            # Preserve running state if the stream connected before REST returned.
            if not session.connected:
                session.state = "waiting_media"
            await session.sync()
        except asyncio.CancelledError:
            session.termination.request("cancelled")
            session.termination.summary.cleanup_status = "uncertain"
            await asyncio.shield(session.finish({"status": "failed", "dispatch_uncertain": True}))
            raise
        except Exception as exc:
            exception_event("voice-runtime", exc)
            session.termination.request("pipeline_failure")
            await session.finish({"status": "failed", "dispatch_uncertain": True})
        finally:
            if session.task is asyncio.current_task():
                session.task = None

    async def close(self):
        self.capacity.draining = True
        tasks = []
        for session in self.sessions.values():
            if not session.closed.is_set():
                if session.task:
                    session.task.cancel()
                    tasks.append(session.task)
                else:
                    tasks.append(asyncio.create_task(session.finish({"status": "failed"})))
        if tasks:
            try:
                async with asyncio.timeout(self.settings.runtime_shutdown_seconds):
                    await asyncio.gather(*tasks, return_exceptions=True)
            except TimeoutError:
                pass
        for task in tuple(self.cleanup_tasks):
            task.cancel()
        await asyncio.gather(*self.cleanup_tasks, return_exceptions=True)
        await self.control_client.aclose()
        await self.upload_client.aclose()
        await self.storage_client.aclose()


@asynccontextmanager
async def lifespan(app):
    settings = get_settings()
    settings.validate_deployment()
    install("voice-runtime")
    configure(
        "voice-runtime",
        "data/logs" if settings.local else None,
        env_files=settings.model_config.get("env_file", ()),
    )
    from voice_runtime.safe_logs import set_event_sink
    from voice_shared.logging import emit

    set_event_sink(lambda event: emit({"service": "voice-runtime", **event}))
    from voice_runtime import perf_diagnostics

    perf_diagnostics.configure(env=settings.env, enabled=settings.debug_perf)
    manager = Manager(settings)
    app.state.manager = manager
    monitor = asyncio.create_task(manager.capacity.monitor())
    loop = asyncio.get_running_loop()
    previous = loop.get_exception_handler()
    loop.set_exception_handler(
        lambda _loop, context: exception_event(
            "voice-runtime", context.get("exception") or RuntimeError()
        )
    )
    try:
        yield
    finally:
        monitor.cancel()
        await asyncio.gather(monitor, return_exceptions=True)
        await manager.close()
        set_event_sink(None)
        loop.set_exception_handler(previous)


app = FastAPI(title="Voice Runtime", version="1.0", lifespan=lifespan)
app.add_middleware(HttpLoggingMiddleware, service="voice-runtime")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        p.strip() for p in get_settings().runtime_allowed_origins.split(",") if p.strip()
    ],
    allow_methods=["GET"],
    allow_headers=[],
)


@app.exception_handler(RequestValidationError)
async def validation_error(request, error):
    return JSONResponse(status_code=422, content={"detail": "Runtime request validation failed"})


async def authenticate(request: Request):
    settings = request.app.state.manager.settings
    value = request.headers.get("X-Voice-Runtime-Control-Token", "")
    if not any(
        token and secrets.compare_digest(value, token)
        for token in (
            settings.runtime_control_token.get_secret_value(),
            settings.runtime_control_token_previous.get_secret_value(),
        )
    ):
        raise HTTPException(401, "Runtime control authentication required")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "voice-runtime"}


@app.get("/v1/status", dependencies=[Depends(authenticate)])
async def status(request: Request):
    return {
        "boot_id": str(request.app.state.manager.boot_id),
        **request.app.state.manager.metrics(),
    }


@app.post("/v1/sessions", dependencies=[Depends(authenticate)])
async def prepare(body: PrepareSession, request: Request):
    s = await request.app.state.manager.prepare(body)
    return {"boot_id": s.boot_id, "generation": s.generation, "state": s.state}


@app.post("/v1/sessions/start", dependencies=[Depends(authenticate)])
async def start(body: SessionIdentity, request: Request):
    m = request.app.state.manager
    return await m.start(m.get(body.run_id, body.generation, body.boot_id))


@app.post("/v1/sessions/stop", dependencies=[Depends(authenticate)])
async def stop(body: SessionIdentity, request: Request):
    s = request.app.state.manager.get(body.run_id, body.generation, body.boot_id)
    s.termination.request("caller_hangup")
    if s.task:
        s.task.cancel()
    elif not s.closed.is_set():
        s.task = asyncio.create_task(s.finish({"status": "failed"}))
    return {"state": s.state}


@app.get("/v1/sessions/{run_id}", dependencies=[Depends(authenticate)])
async def session_status(run_id: str, request: Request):
    s = request.app.state.manager.get(run_id)
    return {
        "state": s.state,
        "generation": s.generation,
        "boot_id": s.boot_id,
        "provider_call_id": s.call_sid,
    }


@app.post("/v1/sessions/text-ticket", dependencies=[Depends(authenticate)])
@app.post("/v1/sessions/browser-ticket", dependencies=[Depends(authenticate)])
async def ticket(body: SessionIdentity, request: Request):
    s = request.app.state.manager.get(body.run_id, body.generation, body.boot_id)
    if (
        s.request.channel not in {"browser", "text_test"}
        or s.connected
        or s.state not in {"waiting_media", "running"}
    ):
        raise HTTPException(409, "Browser session unavailable")
    ticket = secrets.token_urlsafe(32)
    s.ticket_hash = hashlib.sha256(ticket.encode()).hexdigest()
    s.ticket_until = time.monotonic() + 30
    base = (
        s.manager.settings.runtime_public_base_url.replace("https://", "wss://")
        .replace("http://", "ws://")
        .rstrip("/")
    )
    route = "text" if s.request.channel == "text_test" else "browser"
    return {"ticket": ticket, "ws_url": f"{base}/v1/{route}/{s.run_id}?ticket={ticket}"}


@app.websocket("/v1/browser/{run_id}")
async def browser(websocket: WebSocket, run_id: str):
    m = websocket.app.state.manager
    s = m.sessions.get(run_id)
    allowed = [p.strip() for p in m.settings.runtime_allowed_origins.split(",") if p.strip()]
    async with m.lock:
        valid = (
            s
            and s.request.channel == "browser"
            and s.state == "waiting_media"
            and not s.connected
            and s.ticket_hash
            and time.monotonic() < s.ticket_until
            and websocket.headers.get("origin") in allowed
            and secrets.compare_digest(
                s.ticket_hash,
                hashlib.sha256(websocket.query_params.get("ticket", "").encode()).hexdigest(),
            )
        )
        if valid:
            s.ticket_hash = None
            s.connected = True
    if not valid:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    from pipecat.serializers.protobuf import ProtobufFrameSerializer
    from pipecat.transports.websocket.fastapi import (
        FastAPIWebsocketParams,
        FastAPIWebsocketTransport,
    )

    transport = FastAPIWebsocketTransport(
        websocket,
        FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            serializer=ProtobufFrameSerializer(),
            allowed_origins=allowed,
        ),
    )

    @transport.event_handler("on_client_disconnected")
    async def disconnected(_transport, _client):
        s.termination.request("disconnect_unknown")
        if s.task:
            s.task.cancel()

    await s.run_pipeline(transport)


@app.websocket("/api/v1/telephony/twilio/media/{correlation_id}")
async def twilio(websocket: WebSocket, correlation_id: str):
    from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams
    from voice_runtime.telephony.twilio import PublicTelephonyUrls, TwilioCredentials
    from voice_runtime.telephony.twilio_protocol import read_twilio_start, validate_twilio_signature
    from voice_runtime.telephony.twilio_rest import TwilioRestCall
    from voice_runtime.telephony.twilio_session import (
        ManagedTwilioSerializer,
        ManagedTwilioTransport,
        TwilioMediaSession,
    )

    m = websocket.app.state.manager
    s = next(
        (
            s
            for s in m.sessions.values()
            if s.request.channel == "twilio" and s.request.correlation_id == correlation_id
        ),
        None,
    )
    if not s or s.connected or s.state not in {"starting", "waiting_media"}:
        await websocket.close(code=1008)
        return
    creds = TwilioCredentials(
        **{k: v.get_secret_value() for k, v in s.request.telephony_credentials.items()}
    )
    canonical = PublicTelephonyUrls(m.settings.runtime_public_base_url).twilio_media(correlation_id)
    if not validate_twilio_signature(
        creds.auth_token,
        canonical,
        {},
        websocket.headers.get("x-twilio-signature", ""),
        websocket=True,
    ):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    try:
        call_sid, stream_sid = await read_twilio_start(
            websocket,
            account_sid=creds.account_sid,
            expected_call_sid=s.call_sid,
            expected_stream_sid=None,
            run_id=s.run_id,
            correlation_id=correlation_id,
        )
    except Exception:
        await websocket.close(code=1008)
        return
    async with m.lock:
        if s.connected or s.state not in {"starting", "waiting_media"}:
            await websocket.close(code=1008)
            return
        s.connected = True
        s.call_sid = call_sid
    rest = TwilioRestCall(creds, call_sid)
    s.media = TwilioMediaSession(stream_sid, s.termination, websocket.send_json, rest)
    serializer = ManagedTwilioSerializer(
        s.media, sample_rate=s.request.snapshot.get("audio", {}).get("sample_rate", 16000)
    )
    transport = ManagedTwilioTransport(
        websocket,
        FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            serializer=serializer,
            allowed_origins=[],
        ),
    )

    @transport.event_handler("on_client_disconnected")
    async def disconnected(_transport, _ws):
        s.media.disconnected()

    await s.run_pipeline(transport, s.media)


@app.post("/v1/modems/probe", dependencies=[Depends(authenticate)])
async def probe_modem(body: ModemProbe, request: Request):
    from dataclasses import asdict
    from datetime import UTC, datetime

    from voice_runtime.telephony.sim7600 import Sim7600Modem

    m = request.app.state.manager
    if not m.settings.local:
        raise HTTPException(404, "SIM7600 unavailable in hosted environments")
    ports = {body.at_port.casefold(), body.audio_port.casefold()}
    async with m.lock:
        occupied = {
            port
            for s in m.sessions.values()
            if s.state != "ended" and s.request.channel == "sim7600"
            for port in s.modem_ports
        }
        if ports & (occupied | m.probe_ports) or body.at_port == body.audio_port:
            raise HTTPException(409, "Modem is busy")
        m.probe_ports.update(ports)
    modem = Sim7600Modem(body.at_port, body.baudrate, command_timeout=body.at_timeout_secs)
    try:
        async with asyncio.timeout(30):
            status = asdict(await modem.probe_status())
            status.pop("available_transports", None)
            status["call_state"] = status["call_state"].value
            return {"status": status}
    except Exception as exc:
        exception_event("voice-runtime", exc)
        return {
            "status": {
                "alive": False,
                "serial_connected": False,
                "checked_at": datetime.now(UTC),
                "last_error": "Modem probe failed; inspect runtime diagnostics",
            }
        }
    finally:
        try:
            await modem.close()
        finally:
            async with m.lock:
                m.probe_ports.difference_update(ports)


@app.websocket("/v1/text/{run_id}")
async def text_socket(websocket: WebSocket, run_id: str):
    from fastapi import WebSocketDisconnect

    from voice_runner.text import run_text

    m = websocket.app.state.manager
    s = m.sessions.get(run_id)
    allowed = [p.strip() for p in m.settings.runtime_allowed_origins.split(",") if p.strip()]
    async with m.lock:
        valid = (
            s
            and s.text
            and not s.text.paused
            and not s.closed.is_set()
            and not s.connected
            and s.state in {"waiting_media", "running"}
            and s.ticket_hash
            and time.monotonic() < s.ticket_until
            and websocket.headers.get("origin") in allowed
            and secrets.compare_digest(
                s.ticket_hash,
                hashlib.sha256(websocket.query_params.get("ticket", "").encode()).hexdigest(),
            )
        )
        if valid:
            s.ticket_hash = None
            s.connected = True
    if not valid:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    state = s.text
    if state.disconnect_task:
        state.disconnect_task.cancel()
    try:
        after = int(websocket.query_params.get("after", "0"))
    except ValueError:
        after = 0
    if after and state.replay and after < state.replay[0]["sequence"] - 1:
        await websocket.send_json(
            {
                "type": "error",
                "stage": "connection",
                "message": "Replay window expired. Reload saved history before reconnecting.",
                "diagnostic_id": str(uuid4()),
            }
        )
        await websocket.close(code=1008)
        s.connected = False
        state.disconnect_task = asyncio.create_task(state.disconnected())
        return
    state.queue = asyncio.Queue(maxsize=512)
    for event in state.replay:
        if event["sequence"] > after:
            await websocket.send_json(event)
    if not s.task:
        s.task = asyncio.create_task(run_text(s), name=f"text-{run_id}")
    queue = state.queue

    async def sender():
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), 20)
            except TimeoutError:
                if state.queue is None:
                    await websocket.close(code=1013)
                    return
                await websocket.send_json({"type": "heartbeat"})
                continue
            await websocket.send_json(event)
            if event.get("type") == "state" and event.get("state") in {"paused", "ended", "failed"}:
                await websocket.close(code=1000)
                return

    sender_task = asyncio.create_task(sender())

    async def receive():
        await state.ready.wait()
        if not s.host or s.closed.is_set():
            return
        while True:
            raw = await websocket.receive_text()
            try:
                import json

                if len(raw) > 12000:
                    raise ValueError("Message exceeds the input limit")
                body = json.loads(raw)
                if not isinstance(body, dict):
                    raise ValueError("Expected a chat command")
                await state.command(body)
            except (ValueError, TypeError):
                state.emit(
                    {
                        "type": "error",
                        "stage": "input",
                        "message": "Invalid chat command. Enter a message of 1 to 8000 characters.",
                        "diagnostic_id": str(uuid4()),
                    }
                )
            except Exception as exc:
                exception_event("voice-runtime", exc)
                await state.failure(
                    "runtime",
                    "The message could not be processed. Inspect diagnostics before retrying.",
                )
                if s.task:
                    s.task.cancel()
                return

    receiver_task = asyncio.create_task(receive())
    try:
        done, _ = await asyncio.wait(
            [sender_task, receiver_task], return_when=asyncio.FIRST_COMPLETED
        )
        for task in done:
            try:
                task.result()
            except (WebSocketDisconnect, TimeoutError, RuntimeError):
                pass
    finally:
        for task in (sender_task, receiver_task):
            task.cancel()
        await asyncio.gather(sender_task, receiver_task, return_exceptions=True)
        state.queue = None
        s.connected = False
        if not s.closed.is_set():
            state.disconnect_task = asyncio.create_task(state.disconnected())
