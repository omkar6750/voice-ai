"""Development-only, content-free HTTP phase diagnostics."""

from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
from time import perf_counter
from uuid import uuid4

from voice_runtime.perf_diagnostics import is_enabled, timing
from voice_shared.logging import emit, trace_id


@dataclass
class ReadMetrics:
    milliseconds: dict[str, float] = field(default_factory=dict)
    queries: int = 0
    endpoint_finished: float | None = None
    active: bool = True


current: ContextVar[ReadMetrics | None] = ContextVar("api_read_metrics", default=None)


def record(phase: str, milliseconds: float) -> None:
    metrics = current.get()
    if metrics is not None and metrics.active:
        metrics.milliseconds[phase] = metrics.milliseconds.get(phase, 0) + milliseconds


def timed_read(endpoint):
    @wraps(endpoint)
    async def wrapped(*args, **kwargs):
        result = await endpoint(*args, **kwargs)
        if (metrics := current.get()) is not None:
            metrics.endpoint_finished = perf_counter()
        return result

    return wrapped


class ReadMetricsMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not is_enabled():
            return await self.app(scope, receive, send)
        started = perf_counter()
        request_id = trace_id.get() or uuid4().hex
        metrics = ReadMetrics()
        token = current.set(metrics)
        size = 0

        async def measured_send(message):
            nonlocal size
            if message["type"] == "http.response.start":
                if metrics.endpoint_finished is not None:
                    record("response_build", (perf_counter() - metrics.endpoint_finished) * 1000)
                phases = {**metrics.milliseconds, "total": (perf_counter() - started) * 1000}
                values = ", ".join(f"{phase};dur={value:.2f}" for phase, value in phases.items())
                values += f', queries;desc="{metrics.queries}"'
                message["headers"] = [
                    *message.get("headers", []),
                    (b"server-timing", values.encode()),
                    (b"x-request-id", request_id.encode()),
                ]
            elif message["type"] == "http.response.body":
                size += len(message.get("body", b""))
            await send(message)

        try:
            await self.app(scope, receive, measured_send)
        finally:
            timing("api", "read", (perf_counter() - started) * 1000, count=size)
            # Deliberately fixed metadata only: no URLs, headers, identifiers
            # from callers, SQL, parameters, or response contents enter this log.
            emit(
                {
                    "event": "api_read_timing",
                    "service": "voice-api",
                    "trace_id": request_id,
                    "duration_ms": round((perf_counter() - started) * 1000, 2),
                    "query_count": metrics.queries,
                    "response_bytes": size,
                    "phases_ms": {
                        key: round(value, 2) for key, value in metrics.milliseconds.items()
                    },
                },
                forward=False,
            )
            # Spawned tasks inherit contextvars; they must stop contributing
            # once this HTTP response has ended.
            metrics.active = False
            current.reset(token)
