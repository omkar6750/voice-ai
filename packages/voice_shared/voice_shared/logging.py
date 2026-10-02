"""Bounded, nonblocking HTTP diagnostics; unknown strings are private by default."""

from __future__ import annotations

import contextvars
import json
import logging
import logging.handlers
import os
import queue
import re
import time
import traceback
from pathlib import Path
from uuid import UUID, uuid4

run_id = contextvars.ContextVar("voice_run_id", default="")
trace_id = contextvars.ContextVar("voice_trace_id", default="")
parent_span = contextvars.ContextVar("voice_parent_span", default="")
child_spans = contextvars.ContextVar("voice_child_spans", default=None)
# Retain numbers/booleans and safe protocol enumerations; arbitrary text is private.
PRIVATE = re.compile(
    r"key|secret|token|authorization|cookie|password|cipher|signature|ticket|grant|prompt|transcript|content|text|message|phone|email|name|arguments|snapshot|credential|payload|context|url|path|reason",
    re.I,
)
SAFE_STRINGS = {
    "status",
    "service",
    "direction",
    "method",
    "provider",
    "category",
    "event",
    "error_type",
    "trace_id",
    "span_id",
    "parent_span_id",
    "run_id",
    "boot_id",
    "generation",
    "diagnostic_id",
    "origin_service",
    "module",
    "function",
    "level",
}
logger = logging.getLogger("voice.http")
logger.propagate = False
_listener = None
_bounded_handler = None
_subscribers = set()
_dropped = 0
_environment = {}


def enabled(name):
    return os.getenv("VOICE_" + name, _environment.get("VOICE_" + name, "false")).lower() in {
        "true",
        "1",
        "yes",
    }


class SafePreview(str):
    """Only constructed from redacted JSON, never untrusted text."""


def redact(value, key=""):
    if isinstance(value, SafePreview):
        return value
    if PRIVATE.search(key):
        return "[redacted]"
    if isinstance(value, dict):
        return {
            str(k)
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]{0,79}", str(k))
            else "private_field": redact(v, str(k))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact(v, key) for v in value]
    if isinstance(value, str):
        if key in SAFE_STRINGS and re.fullmatch(r"[A-Za-z0-9_.:-]{1,150}", value):
            return value
        return "[redacted]"
    if value is None or isinstance(value, (int, float, bool)):
        return value
    return "[redacted]"


class BoundedHandler(logging.handlers.QueueHandler):
    def enqueue(self, record):
        global _dropped
        try:
            self.queue.put_nowait(record)
        except queue.Full:
            _dropped += 1


def configure(service, directory=None, *, env_files=()):
    global _listener, _bounded_handler
    from dotenv import dotenv_values

    for env_file in env_files or ():
        _environment.update(
            {
                k: v
                for k, v in dotenv_values(env_file).items()
                if k
                in {
                    "VOICE_ENABLE_INBOUND_API_LOGS",
                    "VOICE_ENABLE_OUTBOUND_API_LOGS",
                    "VOICE_INBOUND_API_LOGS_NO_TRUNCATE",
                    "VOICE_OUTBOUND_API_LOGS_NO_TRUNCATE",
                    "VOICE_API_LOG_MAX_BODY_CHARS",
                    "VOICE_DEBUG_PERF",
                    "VOICE_LOG_LEVEL",
                }
                and v is not None
            }
        )
    logger.propagate = False
    if _listener is not None:
        logger.handlers = [_bounded_handler]
        return
    q = queue.Queue(maxsize=2048)
    sinks = [logging.StreamHandler()]
    if directory:
        Path(directory).mkdir(parents=True, exist_ok=True)
        sinks.append(
            logging.handlers.RotatingFileHandler(
                Path(directory) / f"{service}.jsonl",
                maxBytes=5_000_000,
                backupCount=3,
                encoding="utf-8",
            )
        )
    for sink in sinks:
        sink.setFormatter(logging.Formatter("%(message)s"))
    _bounded_handler = BoundedHandler(q)
    logger.handlers = [_bounded_handler]
    logger.setLevel(os.getenv("VOICE_LOG_LEVEL", _environment.get("VOICE_LOG_LEVEL", "INFO")))
    _listener = logging.handlers.QueueListener(q, *sinks)
    _listener.start()


def emit(event, *, forward=True):
    event = {**event, "run_id": event.get("run_id") or run_id.get()}
    try:
        event["run_id"] = str(UUID(event["run_id"]))
    except (ValueError, TypeError):
        pass
    safe = redact(event)
    level = logging._nameToLevel.get(event.get("level", "INFO"), logging.INFO)
    if logger.isEnabledFor(level):
        logger.handle(
            logging.LogRecord(
                "voice.http",
                level,
                __file__,
                0,
                json.dumps(safe, separators=(",", ":")),
                (),
                None,
            )
        )
    if forward:
        for sink in tuple(_subscribers):
            sink(safe)


def exception_event(service, exc, *, forward=True):
    diagnostic_id = uuid4().hex
    # Do not read exception messages, locals, or credential-bearing filenames.
    emit(
        {
            "event": "unexpected_failure",
            "level": "ERROR",
            "service": service,
            "diagnostic_id": diagnostic_id,
            "trace_id": trace_id.get(),
            "error_type": type(exc).__name__,
            "frames": [
                {"line": f.lineno, "module": Path(f.filename).name, "function": f.name}
                for f in traceback.extract_tb(exc.__traceback__)
            ],
        },
        forward=forward,
    )
    return diagnostic_id


def body_preview(body, direction, metadata_only=False):
    if metadata_only:
        return {"bytes": len(body), "body": "[metadata-only]"}
    try:
        safe = redact(json.loads(body))
    except (ValueError, UnicodeError):
        safe = {"bytes": len(body), "body": "[non-json]"}
    rendered = json.dumps(safe, separators=(",", ":"))
    maximum = max(
        128,
        int(
            os.getenv(
                "VOICE_API_LOG_MAX_BODY_CHARS",
                _environment.get("VOICE_API_LOG_MAX_BODY_CHARS", "8192"),
            )
        ),
    )
    if not enabled(direction.upper() + "_API_LOGS_NO_TRUNCATE") and len(rendered) > maximum:
        return {
            "truncated": True,
            "total_chars": len(rendered),
            "preview": SafePreview(rendered[:maximum]),
        }
    return safe


class HttpLoggingMiddleware:
    """Observe JSON without consuming streams; response event remains ASGI-streamed."""

    def __init__(self, app, service):
        self.app, self.service = app, service

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        incoming = headers.get(b"traceparent", b"").decode("ascii", "ignore")
        match = re.fullmatch(r"00-([a-f0-9]{32})-([a-f0-9]{16})-01", incoming)
        trace = match[1] if match else uuid4().hex
        span = uuid4().hex[:16]
        tokens = (trace_id.set(trace), parent_span.set(span), child_spans.set([]))
        started, status = time.monotonic(), 500
        body_in, body_out = bytearray(), bytearray()
        log = enabled("ENABLE_INBOUND_API_LOGS")
        metadata_only = (
            "sync" in scope["path"]
            or "upload" in scope["path"]
            or b"application/json" not in headers.get(b"content-type", b"")
        )
        response_json = False
        limit = float("inf") if enabled("INBOUND_API_LOGS_NO_TRUNCATE") else 65536

        async def observed_receive():
            event = await receive()
            if (
                log
                and not metadata_only
                and event["type"] == "http.request"
                and len(body_in) < limit
            ):
                body_in.extend(
                    event.get("body", b"")
                    if limit == float("inf")
                    else event.get("body", b"")[: int(limit) - len(body_in)]
                )
            return event

        async def observed_send(event):
            nonlocal status, response_json
            if event["type"] == "http.response.start":
                status = event["status"]
                response_json = b"application/json" in dict(event.get("headers", [])).get(
                    b"content-type", b""
                )
                event["headers"] = [
                    *event.get("headers", []),
                    (b"x-diagnostic-trace-id", trace.encode()),
                ]
            if (
                log
                and not metadata_only
                and response_json
                and event["type"] == "http.response.body"
                and len(body_out) < limit
            ):
                body_out.extend(
                    event.get("body", b"")
                    if limit == float("inf")
                    else event.get("body", b"")[: int(limit) - len(body_out)]
                )
            await send(event)

        try:
            await self.app(scope, observed_receive, observed_send)
        except Exception as exc:
            exception_event(self.service, exc)
            raise
        finally:
            if log:
                emit(
                    {
                        "event": "http_request",
                        "service": self.service,
                        "direction": "inbound",
                        "method": scope["method"],
                        "trace_id": trace,
                        "span_id": span,
                        "parent_span_id": match[2] if match else "",
                        "route": SafePreview(getattr(scope.get("route"), "path", "unknown")),
                        "http_status": status,
                        "duration_ms": (time.monotonic() - started) * 1000,
                        "input": body_preview(body_in, "inbound", metadata_only),
                        "output": body_preview(
                            body_out, "inbound", metadata_only or not response_json
                        ),
                    }
                )
            trace_id.reset(tokens[0])
            parent_span.reset(tokens[1])
            child_spans.reset(tokens[2])


def http_hooks(service):
    async def request(req):
        trace = trace_id.get() or uuid4().hex
        span = uuid4().hex[:16]
        req.headers["traceparent"] = f"00-{trace}-{span}-01"
        req.extensions["voice_span"] = (time.monotonic(), trace, span, parent_span.get())

    async def response(resp):
        if not enabled("ENABLE_OUTBOUND_API_LOGS"):
            return
        started, trace, span, parent = resp.request.extensions["voice_span"]
        # Never consume SDK audio or streaming responses for diagnostics.
        request_body = resp.request.content if resp.request.is_stream_consumed else b""
        response_body = resp.content if resp.is_stream_consumed else b""
        event = {
            "event": "http_request",
            "service": service,
            "direction": "outbound",
            "method": resp.request.method,
            "trace_id": trace,
            "span_id": span,
            "parent_span_id": parent,
            "http_status": resp.status_code,
            "duration_ms": (time.monotonic() - started) * 1000,
            "input": body_preview(request_body, "outbound", "sync" in resp.request.url.path),
            "output": body_preview(response_body, "outbound", "sync" in resp.request.url.path),
        }
        emit(event, forward="sync" not in resp.request.url.path)
        collector = child_spans.get()
        if collector is not None:
            collector.append(redact(event))

    return {"request": [request], "response": [response]}
