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
