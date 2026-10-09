"""Content never crosses the operational boundary, even with unfamiliar secrets."""

import ast
import io
import json
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from loguru import logger
from pipecat.frames.frames import ErrorFrame, TextFrame, TranscriptionFrame
from pipecat.observers.base_observer import FramePushed
from pipecat.processors.frame_processor import FrameDirection
from voice_runtime.call_capture import CallCapture
from voice_runtime.execution.exchange import ExchangeTracker
from voice_runtime.execution.observer import EvidenceObserver
from voice_runtime.safe_logs import (
    RuntimeEvent,
    configure_safe_logging,
    error_category,
    opaque_id,
    operational_event,
    safe_event_payload,
)
from voice_runtime.telephony.sim7600 import Sim7600Modem
from voice_runtime.telephony.usb_audio import Sim7600UsbAudioParams, _Sim7600AudioInput

SENTINELS = (
    "unknown-secret-canary-Z73",
    "+919876543210",
    "private-query-canary",
    "private-prompt-canary",
    "private-transcript-canary",
    "private-tool-args-results-canary",
    "https://vendor.invalid/path?credential=vendor-url-canary",
)
PRIVATE = " ".join(SENTINELS)


@pytest.fixture
def sinks(tmp_path):
    console = io.StringIO()
    path = tmp_path / "sdk-pipeline.log"
    root = logging.getLogger()
    previous = list(root.handlers), root.level
    previous_factory = logging.getLogRecordFactory()
    entries = {
        name: (list(entry.handlers), entry.propagate)
        for name, entry in logging.Logger.manager.loggerDict.items()
        if isinstance(entry, logging.Logger)
    }
    configure_safe_logging(console=console, pipeline_path=path, level="DEBUG")
    yield console, path
    logger.remove()
    logger.configure(patcher=None)
    logging.setLogRecordFactory(previous_factory)
    root.handlers[:], root.level = previous
    for name, (handlers, propagate) in entries.items():
        entry = logging.getLogger(name)
        entry.handlers[:], entry.propagate = handlers, propagate


def assert_safe(text):
    for sentinel in SENTINELS:
        assert sentinel not in text
    assert "Traceback" not in text
    return [json.loads(line) for line in text.splitlines()]


def test_sdk_stdlib_loguru_and_forged_safe_extras_never_reach_sinks(sinks):
    console, path = sinks
    try:
        settings = {"api_key": PRIVATE}  # noqa: F841 -- traceback-local canary
        raise RuntimeError(PRIVATE)
    except RuntimeError:
        logger.bind(payload=PRIVATE).exception(PRIVATE)
        logger.bind(_operational_token=True, _operational_payload={"event": PRIVATE}).error(PRIVATE)
        for name in ("httpx", "httpcore", "groq", "google.genai", "pipecat", "uvicorn.error"):
            logging.getLogger(name).exception("SDK body %s", PRIVATE, extra={"payload": PRIVATE})
    identifier = uuid4()
    operational_event(
        RuntimeEvent.MESSAGE_ACCEPTED,
        status="accepted",
        run_id=identifier,
        duration_ms=12.5,
        body=PRIVATE,
    )
    for output in (console.getvalue(), path.read_text()):
        records = assert_safe(output)
        assert sum(item["event"] == "untrusted_log" for item in records) == 8
        assert records[-1] == {
            "event": "message_accepted",
            "status": "accepted",
            "run_id": identifier.hex,
            "duration_ms": 12.5,
            "level": "INFO",
        }


def test_safe_fields_reject_payloads_and_never_stringify_objects(sinks):
    class Poison(RuntimeError):
        def __str__(self):
            raise AssertionError("exception text was accessed")

    exc = Poison(PRIVATE)
    logger.opt(exception=exc).error("vendor failure")
    logging.getLogger("vendor.new").error(exc, exc_info=(Poison, exc, None))
    assert error_category(exc) == "runtime"
    operational_event(
        RuntimeEvent.RETRIEVAL_FAILED,
        level="ERROR",
        error_category=error_category(exc),
        query=PRIVATE,
        exception=exc,
    )
    fields = {
        key: PRIVATE
        for key in (
            "provider",
            "status",
            "direction",
            "operation",
            "error_category",
            "run_id",
            "http_status",
            "duration_ms",
            "bytes",
            "processor",
            "strategy",
            "failed_generation",
        )
    }
    assert safe_event_payload(RuntimeEvent.PROVIDER_FAILED, **fields) == {
        "event": "provider_failed"
    }
    assert safe_event_payload(PRIVATE, **fields) == {"event": "untrusted_log"}
    assert opaque_id(PRIVATE) is None
    identifier = uuid4()
    assert opaque_id(str(identifier)) == identifier
    assert safe_event_payload(RuntimeEvent.TOOL_FAILED, duration_ms=float("nan"), count=True) == {
        "event": "tool_failed"
    }
    for output in (sinks[0].getvalue(), sinks[1].read_text()):
        assert_safe(output)


def test_untrusted_vendor_info_spam_is_dropped_but_warning_keeps_severity(sinks):
    console, path = sinks
    logger.info("verbose vendor details that cannot be safely shown")
    logger.warning("vendor warning details that cannot be safely shown")
    for output in (console.getvalue(), path.read_text()):
        records = assert_safe(output)
        assert len(records) == 1
        assert records[0] == {"event": "untrusted_log", "level": "WARNING"}


def test_validation_diagnostic_event_accepts_only_allowlisted_locations():
    assert safe_event_payload(
        RuntimeEvent.API_VALIDATION_FAILED,
        validation_scope="request_query",
        validation_field="limit",
        submitted_value=PRIVATE,
    ) == {
        "event": "api_validation_failed",
        "validation_scope": "request_query",
        "validation_field": "limit",
    }
    assert safe_event_payload(
        RuntimeEvent.API_VALIDATION_FAILED,
        validation_scope=PRIVATE,
        validation_field=PRIVATE,
    ) == {"event": "api_validation_failed"}


def test_existing_sdk_handlers_and_late_loguru_message_patches_are_safe(sinks):
    console, path = sinks
    raw = io.StringIO()
    vendor = logging.getLogger("vendor.custom")
    vendor.addHandler(logging.StreamHandler(raw))
    vendor.propagate = False
    configure_safe_logging(console=console, pipeline_path=path, level="DEBUG")
    vendor.error(PRIVATE)
    logger.patch(lambda record: record.update(message=PRIVATE)).error(PRIVATE)
    assert raw.getvalue() == ""
    for output in (console.getvalue(), path.read_text()):
        assert len(assert_safe(output)) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("raises", [False, True])
async def test_native_vendor_body_url_and_exception_remain_out_of_logs(sinks, monkeypatch, raises):
    import voice_runtime.execution.native_helpers as native_helpers

    client = AsyncMock()
    client.__aenter__.return_value = client
    if raises:
        client.post.side_effect = RuntimeError(PRIVATE)
    else:
        client.post.return_value = httpx.Response(
            429, json={"error": {"message": PRIVATE}}, headers={"x-request-id": PRIVATE}
        )
    monkeypatch.setattr(native_helpers.httpx, "AsyncClient", lambda **kwargs: client)
    result = await native_helpers.run_jev_classification(
        PRIVATE, PRIVATE, {"prompt": PRIVATE}, api_url=SENTINELS[-1]
    )
    assert result["status"] == "error"
    assert client.post.call_args.args[0] == SENTINELS[-1]
    assert client.post.call_args.kwargs["json"]["state"] == PRIVATE
    for output in (sinks[0].getvalue(), sinks[1].read_text()):
        records = assert_safe(output)
        event = next(record for record in records if record["event"] == "provider_failed")
        assert event["provider"] == "jev"
        assert (
            event.get("error_category") == "runtime" if raises else event.get("http_status") == 429
        )


def test_modem_raw_response_is_evidence_not_an_operational_log(sinks):
    class Serial:
        def write(self, payload):
            self.payload = payload
            self.responses = iter([(PRIVATE + "\r\n").encode(), b"OK\r\n"])

        def readline(self):
            return next(self.responses)

    modem = Sim7600Modem("fake")
    modem._serial = Serial()
    result = modem._command_sync("ATD" + SENTINELS[1] + ";")
    assert result == [PRIVATE, "OK"]
    for output in (sinks[0].getvalue(), sinks[1].read_text()):
        records = assert_safe(output)
        assert records[-1]["response"] == "ok"
        assert records[-1]["at_command"] == "ATD<number>;"
        assert records[-1]["at_response_line"] == "OK"


def test_modem_status_logs_show_safe_command_and_response(sinks):
    modem = Sim7600Modem("fake")
    modem._serial = type(
        "Serial",
        (),
        {
            "write": lambda self, payload: setattr(
                self, "responses", iter([b"+CSQ: 18,0\r\n", b"OK\r\n"])
            ),
            "readline": lambda self: next(self.responses),
        },
    )()
    modem._command_sync("AT+CSQ")
    records = assert_safe(sinks[0].getvalue())
    command = next(row for row in records if row["event"] == "modem_command")
    response = next(row for row in records if row["event"] == "modem_response")
    assert command["at_command"] == "AT+CSQ"
    assert response["at_response_line"] == "+CSQ: 18,0"


def test_pcm_io_emits_periodic_read_write_totals(sinks):
    import time

    from voice_runtime.telephony.usb_audio import Sim7600UsbAudioParams, _SerialPcmOwner

    owner = _SerialPcmOwner(Sim7600UsbAudioParams(audio_port="COM7"))
    owner._io_summary["input"] = {
        "started": time.monotonic() - 5,
        "bytes": 6400,
        "samples": 3200,
        "count": 10,
    }
    owner._record_io("input", b"\x00\x00" * 320, 16000)
    records = assert_safe(sinks[0].getvalue())
    summary = next(row for row in records if row["event"] == "pcm_io_summary")
    assert summary["direction"] == "input"
    assert summary["phase"] == "read"
    assert summary["bytes"] == 7040
    assert summary["samples"] == 3520
    assert summary["sample_rate"] == 16000


@pytest.mark.asyncio
async def test_observer_pipeline_errors_keep_business_evidence_separate(sinks, tmp_path):
    evidence = SimpleNamespace(records=[])
    evidence.submit = evidence.records.append
    tracker = ExchangeTracker("run-1", evidence)
    tracker.begin("caller")
    llm, stt, tts = SimpleNamespace(), SimpleNamespace(), SimpleNamespace()
    path = tmp_path / "pipeline.log"
    observer = EvidenceObserver(
        tracker,
        llm=llm,
        stt=stt,
        tts=tts,
        llm_model=PRIVATE,
        stt_model=PRIVATE,
        tts_model=PRIVATE,
        log_path=path,
    )
    observer._mark(
        "provider_error",
        provider="groq",
        operation="llm",
        http_status=429,
        failed_generation=PRIVATE,
        provider_request_id=PRIVATE,
        code=PRIVATE,
        error=PRIVATE,
    )
    observer._mark(PRIVATE, text=PRIVATE)
    observer.stt_operation = tracker.start_operation("transcription", "stt")
    await observer.on_push_frame(
        FramePushed(
            source=stt,
            destination=llm,
            frame=TranscriptionFrame(PRIVATE, "user", "time", finalized=True),
            direction=FrameDirection.DOWNSTREAM,
            timestamp=0,
        )
    )
    await observer.on_push_frame(
        FramePushed(
            source=llm,
            destination=tts,
            frame=ErrorFrame(PRIVATE, exception=RuntimeError(PRIVATE)),
            direction=FrameDirection.DOWNSTREAM,
            timestamp=0,
        )
    )
    observer.close()
    records = assert_safe(path.read_text())
    assert records[0] == {
        "event": "provider_error",
        "provider": "groq",
        "operation": "llm",
        "http_status": 429,
    }
    assert records[1] == {"event": "untrusted_log"}
    assert "private-transcript-canary" in json.dumps(evidence.records)
    assert any(record.get("kind") == "diagnostic" for record in evidence.records)
    assert_safe(
        "\n".join(
            json.dumps(record) for record in evidence.records if record.get("kind") == "diagnostic"
        )
    )
    for output in (sinks[0].getvalue(), sinks[1].read_text()):
        assert_safe(output)


@pytest.mark.asyncio
async def test_capture_text_and_error_frames_never_log_content(sinks, tmp_path):
    capture = CallCapture(tmp_path)
    for frame in (TextFrame(PRIVATE), ErrorFrame(PRIVATE)):
        await capture.on_push_frame(
            FramePushed(
                source=SimpleNamespace(name=PRIVATE),
                destination=SimpleNamespace(name=PRIVATE),
                frame=frame,
                direction=FrameDirection.DOWNSTREAM,
                timestamp=0,
            )
        )
    capture.close()
    for output in (sinks[0].getvalue(), sinks[1].read_text()):
        assert any(record["event"] == "frame_observed" for record in assert_safe(output))


@pytest.mark.asyncio
async def test_serial_exception_cannot_sneak_into_pipecat_error_frame(sinks):
    owner = AsyncMock()
    owner.read.side_effect = OSError(PRIVATE)
    processor = _Sim7600AudioInput(owner, Sim7600UsbAudioParams(audio_port=PRIVATE))
    processor.push_error = AsyncMock()
    await processor._read_loop()
    processor.push_error.assert_awaited_once_with("PCM read failed", fatal=True)
    for output in (sinks[0].getvalue(), sinks[1].read_text()):
        assert any(
            record["event"] == "pcm_read_failed" and record["error_category"] == "io"
            for record in assert_safe(output)
        )


@pytest.mark.asyncio
async def test_native_pipeline_failure_does_not_persist_arbitrary_exception_text(sinks, tmp_path):
    from unittest.mock import Mock

    from voice_runtime.execution.native import NativePipelineHost

    class Poison(RuntimeError):
        def __str__(self):
            raise AssertionError("pipeline exception was stringified")

    host = NativePipelineHost("run-1", tmp_path, SimpleNamespace())
    host.worker = SimpleNamespace(cancel=AsyncMock())
    host.tracker = Mock()
    await host._pipeline_failed(SimpleNamespace(error=Poison(PRIVATE)))
    host.worker.cancel.assert_awaited_once()
    assert host.termination.summary.cause == "pipeline_failure"
    assert host.errors == ["Pipeline failed; inspect structured diagnostics"]
    assert_safe(json.dumps(host.tracker.diagnostic.call_args.kwargs))
    for output in (sinks[0].getvalue(), sinks[1].read_text()):
        assert_safe(output)


def test_runtime_log_sites_use_only_the_trusted_event_helper():
    runtime = Path(__file__).resolve().parents[2] / "packages" / "voice_runtime" / "voice_runtime"
    for path in runtime.rglob("*.py"):
        if path.name == "safe_logs.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
            ):
                assert node.func.value.id not in {"logger", "logging"}, (
                    f"raw log in {path}:{node.lineno}"
                )
