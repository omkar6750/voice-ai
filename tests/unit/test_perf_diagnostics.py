from uuid import uuid4

from voice_runtime.safe_logs import RuntimeEvent, safe_event_payload

from voice_runtime import perf_diagnostics


def test_perf_probes_are_development_only_and_scoped(monkeypatch):
    emitted = []
    monkeypatch.setattr(
        perf_diagnostics,
        "operational_event",
        lambda event, **fields: emitted.append((event, fields)),
    )
    run_id = str(uuid4())
    try:
        perf_diagnostics.configure(env="production", enabled=True)
        with perf_diagnostics.call_scope(run_id, "browser"):
            perf_diagnostics.timing("browser_audio", "gap", 83)
        assert emitted == []

        perf_diagnostics.configure(env="dev", enabled=True)
        with perf_diagnostics.call_scope(run_id, "browser"):
            perf_diagnostics.timing("browser_audio", "gap", 83)
        assert len(emitted) == 1
        event, fields = emitted[0]
        assert event is RuntimeEvent.PERF_TIMING
        assert fields["run_id"].hex == run_id.replace("-", "")
        assert fields["transport"] == "browser"
        assert fields["at_ms"] > 0
        assert safe_event_payload(event, **fields)["component"] == "browser_audio"
        assert safe_event_payload(event, **fields)["duration_ms"] == 83
    finally:
        perf_diagnostics.configure(env="dev", enabled=False)


def test_perf_log_allowlist_omits_content():
    event = safe_event_payload(
        RuntimeEvent.PERF_TIMING,
        component="api",
        phase="request",
        route_group="runs",
        request_method="GET",
        http_status=200,
        duration_ms=45,
        at_ms=1_790_000_000_000,
        path="/runs/private-id",
        token="secret",
    )
    assert event == {
        "event": "perf_timing",
        "component": "api",
        "phase": "request",
        "route_group": "runs",
        "request_method": "GET",
        "http_status": 200,
        "duration_ms": 45,
        "at_ms": 1_790_000_000_000,
    }


async def test_loop_monitor_ignores_normal_jitter_but_reports_slow_windows(monkeypatch):
    import asyncio

    import pytest

    emitted = []
    monkeypatch.setattr(
        perf_diagnostics, "timing", lambda *args, **kwargs: emitted.append((args, kwargs))
    )

    class Clock:
        now = 0.0

        def time(self):
            return self.now

    clock = Clock()
    monkeypatch.setattr(asyncio, "get_running_loop", lambda: clock)
    perf_diagnostics.configure(env="dev", enabled=True)
    try:
        for lag in (0.027, 0.050):
            calls = 0

            async def sleep(interval, delay=lag):
                nonlocal calls
                calls += 1
                if calls > 120:
                    raise asyncio.CancelledError
                clock.now += interval + delay

            monkeypatch.setattr(asyncio, "sleep", sleep)
            with pytest.raises(asyncio.CancelledError):
                await perf_diagnostics.loop_lag_monitor()
            if lag < 0.04:
                assert emitted == []
            else:
                assert emitted
                assert emitted[0][0][:2] == ("loop", "lag")
                assert emitted[0][1]["count"] > 0
    finally:
        perf_diagnostics.configure(env="dev", enabled=False)
