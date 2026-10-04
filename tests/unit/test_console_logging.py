import io
import json
import logging

from voice_runtime.safe_logs import RuntimeEvent, safe_event_payload
from voice_shared.logging import ConsoleFormatter, redact, round_timings


def record(event):
    return logging.LogRecord("voice.http", logging.INFO, __file__, 0, json.dumps(event), (), None)


def test_pretty_nested_logs_keep_redaction_precision_and_direction_colors(monkeypatch):
    monkeypatch.setenv("VOICE_LOG_FORMAT", "pretty")
    monkeypatch.setenv("VOICE_LOG_COLOR", "always")
    formatter = ConsoleFormatter(io.StringIO())
    for direction, color in (("inbound", "36"), ("outbound", "35")):
        event = round_timings(
            redact(
                {
                    "event": "http_request",
                    "service": "voice-api",
                    "direction": direction,
                    "http_status": 200,
                    "duration_ms": 27.000000001862645,
                    "input": {"api_key": "secret-canary", "nested": {"count": 2}},
                    "phases_ms": {"query": 1.23456789},
                }
            )
        )
        output = formatter.format(record(event))
        assert f"\x1b[{color}m" in output
        assert direction in output
        assert "27.0000 ms" in output
        assert "query: 1.2346 ms" in output
        assert "|- input:" in output and "|- nested:" in output
        assert "secret-canary" not in output
        assert "[redacted]" in output
        assert event["phases_ms"]["query"] == 1.2346


def test_json_mode_remains_machine_readable_and_non_tty_auto_has_no_ansi(monkeypatch):
    monkeypatch.setenv("VOICE_LOG_FORMAT", "auto")
    monkeypatch.setenv("VOICE_LOG_COLOR", "auto")
    event = {"event": "http_request", "duration_ms": 27.0}
    output = ConsoleFormatter(io.StringIO()).format(record(event))
    assert json.loads(output) == event
    assert "\x1b" not in output


def test_runtime_timings_have_bounded_precision():
    event = safe_event_payload(RuntimeEvent.PERF_TIMING, duration_ms=27.000000001862645)
    assert event["duration_ms"] == 27.0
    event = safe_event_payload(RuntimeEvent.PERF_TIMING, duration_ms=1.23456789)
    assert event["duration_ms"] == 1.2346


def test_configure_loads_console_options_and_keeps_file_sink_json(tmp_path, monkeypatch):
    from voice_shared import logging as diagnostics

    env = tmp_path / ".env.local"
    env.write_text(
        "VOICE_LOG_FORMAT=pretty\nVOICE_LOG_COLOR=always\nVOICE_LOG_LEVEL=INFO\n", encoding="utf-8"
    )
    for name in ("VOICE_LOG_FORMAT", "VOICE_LOG_COLOR", "VOICE_LOG_LEVEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(diagnostics, "_environment", {})
    monkeypatch.setattr(diagnostics, "_listener", None)
    monkeypatch.setattr(diagnostics, "_bounded_handler", None)
    previous = (
        diagnostics.logger.handlers[:],
        diagnostics.logger.level,
        diagnostics.logger.propagate,
    )
    try:
        diagnostics.configure("voice-test", tmp_path, env_files=(env,))
        console, file = diagnostics._listener.handlers
        assert console.formatter.pretty
        assert console.formatter.color
        assert diagnostics.logger.level == logging.INFO
        event = {"event": "http_request", "direction": "inbound"}
        assert json.loads(file.format(record(event))) == event
    finally:
        if diagnostics._listener:
            diagnostics._listener.stop()
            for handler in diagnostics._listener.handlers:
                handler.close()
        diagnostics.logger.handlers, diagnostics.logger.level, diagnostics.logger.propagate = (
            previous
        )
