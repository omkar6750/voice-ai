"""Opt-in, content-free timing probes for local call diagnosis."""

from __future__ import annotations

import asyncio
import contextvars
import time
from contextlib import contextmanager
from uuid import UUID

from voice_runtime.safe_logs import RuntimeEvent, operational_event

_enabled = False
_call: contextvars.ContextVar[tuple[UUID, str] | None] = contextvars.ContextVar(
    "voice_perf_call", default=None
)


def configure(*, env: str, enabled: bool) -> None:
    global _enabled
    _enabled = enabled and env.casefold() in {"dev", "development", "local"}


def is_enabled() -> bool:
    return _enabled


@contextmanager
def call_scope(run_id: str, transport: str):
    try:
        identity = UUID(run_id)
    except ValueError:
        identity = None
    token = _call.set((identity, transport) if identity is not None else None)
    try:
        yield
    finally:
        _call.reset(token)


def timing(
    component: str,
    phase: str,
    duration_ms: float,
    *,
    count: int | None = None,
    request_method: str | None = None,
    http_status: int | None = None,
    route_group: str | None = None,
) -> None:
    if not _enabled:
        return
    scope = _call.get()
    operational_event(
        RuntimeEvent.PERF_TIMING,
        component=component,
        phase=phase,
        duration_ms=duration_ms,
        count=count,
        request_method=request_method,
        http_status=http_status,
        route_group=route_group,
        run_id=scope[0] if scope else None,
        transport=scope[1] if scope else "none",
        at_ms=time.time_ns() // 1_000_000,
    )


@contextmanager
def measure(component: str, phase: str):
    if not _enabled:
        yield
        return
    started = time.perf_counter()
    try:
        yield
    finally:
        timing(component, phase, (time.perf_counter() - started) * 1000)


async def loop_lag_monitor() -> None:
    """Summarize scheduling delay without logging on every 20 ms tick."""
    if not _enabled:
        return
    loop = asyncio.get_running_loop()
    interval = 0.02
    window_started = loop.time()
    worst_ms = 0.0
    over_40_ms = 0
    while True:
        target = loop.time() + interval
        await asyncio.sleep(interval)
        lag_ms = max(0.0, (loop.time() - target) * 1000)
        worst_ms = max(worst_ms, lag_ms)
        over_40_ms += lag_ms >= 40
        if loop.time() - window_started >= 5:
            if over_40_ms:
                timing("loop", "lag", worst_ms, count=over_40_ms)
            window_started = loop.time()
            worst_ms = 0.0
            over_40_ms = 0
