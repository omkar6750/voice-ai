"""Task-local request evidence, independent of optional operational logging."""

import contextvars
import json
import time
from uuid import uuid4

import httpx

sink = contextvars.ContextVar("voice_request_evidence_sink", default=None)
operation = contextvars.ContextVar("voice_request_operation", default=None)
capture_payloads = contextvars.ContextVar("voice_request_capture_payloads", default=False)


def is_internal_request(path: str) -> bool:
    """Exclude runtime evidence/recording transport from agent activity.

    Accept the leading :id emitted by older route labels for saved runs too.
    """
    path = path.removeprefix(":id/")
    path = "/" + path.lstrip("/")
    return path.startswith(("/api/v1/runtime/sync", "/api/v1/runtime/artifacts/"))


def is_internal_span(span) -> bool:
    return span.category == "http_request" and is_internal_request(
        (span.attributes or {}).get("endpoint", "")
    )


def json_payload(raw):
    from voice_shared.dev_visibility import is_development

    if (
        (not capture_payloads.get() and not is_development())
        or not isinstance(raw, bytes)
        or len(raw) > 1_000_000
    ):
        return None
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError):
        return None
    return value if isinstance(value, (dict, list)) else {"value": value}


def begin(
    method: str, path: str, service: str, *, input_payload=None, host=None, category="http_request"
):
    callback = sink.get()
    if callback is None or is_internal_request(path) or service == "mcp.internal":
        return None
    from voice_shared.http_clients import route_label

    provider = service
    if host:
        provider = next(
            (
                name
                for name, domain in (
                    ("openai", "openai.com"),
                    ("sarvam", "sarvam.ai"),
                    ("gnani", "gnani.ai"),
                    ("google", "googleapis.com"),
                    ("twilio", "twilio.com"),
                    ("supabase", "supabase.co"),
                    ("meta", "facebook.com"),
                    ("deepgram", "deepgram.com"),
                    ("elevenlabs", "elevenlabs.io"),
                )
                if host == domain or host.endswith("." + domain)
            ),
            "external",
        )
    state = {
        "operation_id": uuid4().hex,
        "parent_id": operation.get(),
        "method": method,
        "endpoint": str(route_label(path)),
        "service": provider,
        "category": category,
        "started_ns": time.time_ns(),
        "clock": time.monotonic_ns(),
        "callback": callback,
        "input_payload": input_payload,
    }
    callback({**state, "phase": "started"})
    return state


def finish(state, *, status=None, error=None, timing_scope="complete", output_payload=None):
    if state is None:
        return
    state["callback"](
        {
            **state,
            "phase": "ended",
            "ended_ns": time.time_ns(),
            "duration_ms": (time.monotonic_ns() - state["clock"]) / 1_000_000,
            "http_status": status,
            "error_type": type(error).__name__ if error else None,
            "timing_scope": timing_scope,
            "output_payload": output_payload,
            "status": "cancelled"
            if isinstance(error, BaseException) and not isinstance(error, Exception)
            else "failed"
            if error or (status and status >= 400)
            else "completed",
        }
    )


class AsyncResponseStream(httpx.AsyncByteStream):
    def __init__(self, stream, state, status):
        self.stream, self.state, self.status = stream, state, status
        self.finished = False

    def end(self, error=None, scope="complete"):
        if not self.finished:
            self.finished = True
            finish(self.state, status=self.status, error=error, timing_scope=scope)

    async def __aiter__(self):
        try:
            async for chunk in self.stream:
                yield chunk
        except BaseException as error:
            self.end(error)
            raise
        else:
            self.end()

    async def aclose(self):
        try:
            await self.stream.aclose()
        finally:
            self.end(scope="closed_before_exhaustion")


class SyncResponseStream(httpx.SyncByteStream):
    def __init__(self, stream, state, status):
        self.stream, self.state, self.status = stream, state, status
        self.finished = False

    def end(self, error=None, scope="complete"):
        if not self.finished:
            self.finished = True
            finish(self.state, status=self.status, error=error, timing_scope=scope)

    def __iter__(self):
        try:
            yield from self.stream
        except BaseException as error:
            self.end(error)
            raise
        else:
            self.end()

    def close(self):
        try:
            self.stream.close()
        finally:
            self.end(scope="closed_before_exhaustion")
