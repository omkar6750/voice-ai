"""Instrument actual SDK HTTP transports without consuming streaming media."""

import time
from functools import wraps
from uuid import uuid4

import httpx

from voice_shared.logging import (
    SafePreview,
    body_preview,
    child_spans,
    emit,
    enabled,
    exception_event,
    parent_span,
    redact,
    trace_id,
)

_installed = False


def route_label(path):
    known = {
        "api",
        "v1",
        "runtime",
        "sync",
        "tools",
        "artifacts",
        "grant",
        "complete",
        "runs",
        "timeline",
        "agents",
        "chat",
        "completions",
        "audio",
        "speech",
        "transcriptions",
        "models",
        "Calls.json",
        "Accounts",
        "messages",
        "calendar",
        "events",
        "freeBusy",
        "storage",
        "object",
        "upload",
        "sign",
    }
    return SafePreview("/".join(part if part in known else ":id" for part in path.split("/")))


def install(service):
    global _installed
    if _installed:
        return
    _installed = True
    original_async = httpx.AsyncClient.send
    original_sync = httpx.Client.send

    def begin(request):
        trace = trace_id.get() or uuid4().hex
        span = uuid4().hex[:16]
        request.headers["traceparent"] = f"00-{trace}-{span}-01"
        return time.monotonic(), trace, span, parent_span.get()

    def report(request, response, state):
        if not enabled("ENABLE_OUTBOUND_API_LOGS"):
            return
        started, trace, span, parent = state
        # Only complete JSON responses are inspected. Streaming/audio stays metadata.
        binary = "application/json" not in response.headers.get("content-type", "")
        metadata = "/runtime/sync" in request.url.path
        event = {
            "event": "http_request",
            "service": service,
            "direction": "outbound",
            "method": request.method,
            "route": route_label(request.url.path),
            "trace_id": trace,
            "span_id": span,
            "parent_span_id": parent,
            "http_status": response.status_code,
            "duration_ms": (time.monotonic() - started) * 1000,
            "input": body_preview(
                request.content if request.is_stream_consumed else b"",
                "outbound",
                metadata or "application/json" not in request.headers.get("content-type", ""),
            ),
            "output": body_preview(
                response.content if response.is_stream_consumed else b"",
                "outbound",
                metadata or binary or not response.is_stream_consumed,
            ),
        }
        emit(event, forward=not metadata)
        collector = child_spans.get()
        if collector is not None and len(collector) < 100:
            collector.append(redact(event))

    @wraps(original_async)
    async def async_send(self, request, *args, **kwargs):
        state = begin(request)
        try:
            response = await original_async(self, request, *args, **kwargs)
        except Exception as exc:
            exception_event(service, exc, forward="/runtime/sync" not in request.url.path)
            raise
        report(request, response, state)
        return response

    @wraps(original_sync)
    def sync_send(self, request, *args, **kwargs):
        state = begin(request)
        try:
            response = original_sync(self, request, *args, **kwargs)
        except Exception as exc:
            exception_event(service, exc, forward="/runtime/sync" not in request.url.path)
            raise
        report(request, response, state)
        return response

    httpx.AsyncClient.send = async_send
    httpx.Client.send = sync_send

    # Twilio's SDK uses requests. Never read its streaming response for logging.
    import requests

    original_requests = requests.Session.send

    @wraps(original_requests)
    def requests_send(self, request, *args, **kwargs):
        started = time.monotonic()
        trace = trace_id.get() or uuid4().hex
        span = uuid4().hex[:16]
        request.headers["traceparent"] = f"00-{trace}-{span}-01"
        try:
            response = original_requests(self, request, *args, **kwargs)
        except Exception as exc:
            exception_event(service, exc)
            raise
        if enabled("ENABLE_OUTBOUND_API_LOGS"):
            event = {
                "event": "http_request",
                "service": service,
                "direction": "outbound",
                "method": request.method,
                "route": route_label(
                    __import__("urllib.parse", fromlist=["urlsplit"]).urlsplit(request.url).path
                ),
                "trace_id": trace,
                "span_id": span,
                "parent_span_id": parent_span.get(),
                "http_status": response.status_code,
                "duration_ms": (time.monotonic() - started) * 1000,
                "input": body_preview(
                    request.body if isinstance(request.body, bytes) else b"", "outbound"
                ),
                "output": body_preview(
                    response.content
                    if not kwargs.get("stream")
                    and "application/json" in response.headers.get("content-type", "")
                    else b"",
                    "outbound",
                    bool(kwargs.get("stream")),
                ),
            }
            emit(event)
            if child_spans.get() is not None and len(child_spans.get()) < 100:
                child_spans.get().append(redact(event))
        return response

    requests.Session.send = requests_send

    # Google discovery clients use httplib2 instead of httpx/requests.
    try:
        import httplib2
    except ImportError:
        return
    original_google = httplib2.Http.request

    @wraps(original_google)
    def google_request(self, uri, method="GET", body=None, headers=None, **kwargs):
        from urllib.parse import urlsplit

        started = time.monotonic()
        trace = trace_id.get() or uuid4().hex
        span = uuid4().hex[:16]
        headers = dict(headers or {})
        headers["traceparent"] = f"00-{trace}-{span}-01"
        try:
            response, data = original_google(
                self, uri, method=method, body=body, headers=headers, **kwargs
            )
        except Exception as exc:
            exception_event(service, exc)
            raise
        if enabled("ENABLE_OUTBOUND_API_LOGS"):
            event = {
                "event": "http_request",
                "service": service,
                "direction": "outbound",
                "method": method,
                "route": route_label(urlsplit(uri).path),
                "trace_id": trace,
                "span_id": span,
                "parent_span_id": parent_span.get(),
                "http_status": int(response.status),
                "duration_ms": (time.monotonic() - started) * 1000,
                "input": body_preview(
                    body.encode() if isinstance(body, str) else body or b"",
                    "outbound",
                    "application/json"
                    not in headers.get("content-type", headers.get("Content-Type", "")),
                ),
                "output": body_preview(
                    data, "outbound", "application/json" not in response.get("content-type", "")
                ),
            }
            emit(event)
            if child_spans.get() is not None and len(child_spans.get()) < 100:
                child_spans.get().append(redact(event))
        return response, data

    httplib2.Http.request = google_request
