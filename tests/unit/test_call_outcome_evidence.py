import asyncio
from queue import Empty, Queue
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from pipecat.processors.frame_processor import FrameProcessor
from voice_runtime.execution.termination import CallTermination
from voice_runtime.execution.voicemail import AnswerDetection
from voice_runtime.telephony.base import CallState
from voice_runtime.telephony.driver import Sim7600CallDriver
from voice_runtime.telephony.outcome import determine_outcome
from voice_runtime.telephony.session import Sim7600ConnectionTimeout
from voice_runtime.telephony.sim7600 import Sim7600Modem
from voice_runtime.telephony.status import ModemStatusReader


def outcome(report=None, signals=()):
    return determine_outcome(
        events=[{"signal": s, "observed_at_ns": i} for i, s in enumerate(signals)],
        report=report,
        errors=[],
        registration={},
    )


@pytest.mark.parametrize(
    ("report", "signals", "reason", "confidence"),
    [
        (None, ["BUSY"], "busy", "confirmed"),
        (None, ["NO ANSWER"], "no_answer", "confirmed"),
        ("User busy", [], "busy", "confirmed"),
        ("Network out of order", [], "network_failure", "confirmed"),
        ("Temporary failure", [], "network_failure", "confirmed"),
        ("Call rejected", [], "call_rejected", "confirmed"),
        ("Normal call clearing", [], "remote_hangup_likely", "likely"),
        ("16", ["NO CARRIER"], "disconnect_unknown", "unknown"),
        ("Network ended call", [], "disconnect_unknown", "unknown"),
        (None, ["NO CARRIER"], "disconnect_unknown", "unknown"),
        (None, ["serial_io_error"], "modem_failure", "confirmed"),
        ("Normal call clearing", ["local_hangup", "NO CARRIER"], "local_hangup", "confirmed"),
        (None, ["BUSY", "local_hangup"], "busy", "confirmed"),
    ],
)
def test_conservative_release_causes(report, signals, reason, confidence):
    result = outcome(report, signals)
    assert (result.reason, result.confidence) == (reason, confidence)


def test_missing_status_is_unknown_not_confirmed_registration_loss():
    missing = ModemStatusReader().from_results({}, serial_connected=True)
    assert not missing.voice_registration_known
    assert not missing.sim_status_known
    actual = ModemStatusReader().from_results({"AT+CREG?": ["+CREG: 0,2"]}, serial_connected=True)
    assert actual.voice_registration_known and not actual.voice_registered


class Port:
    def __init__(self):
        self.lines = Queue()
        self.commands = []
        self.report = b"+CEER: User busy\r\n"
        self.active = False

    def write(self, raw):
        command = raw.decode().strip()
        self.commands.append(command)
        if command == "AT+CEER":
            self.lines.put(self.report)
        elif command == "AT+CREG?":
            self.lines.put(b"+CREG: 1,1\r\n")
        elif command == "AT+CEREG?":
            self.lines.put(b"+CEREG: 1,1\r\n")
        elif command == "AT+CPIN?":
            self.lines.put(b"+CPIN: READY\r\n")
        elif command == "AT+CSQ":
            self.lines.put(b"+CSQ: 18,0\r\n")
        elif command == "AT+CLCC" and self.active:
            self.lines.put(b"+CLCC: 1,0,0,0,0\r\n")
        self.lines.put(b"OK\r\n")

    def readline(self):
        try:
            return self.lines.get(timeout=0.01)
        except Empty:
            return b""

    def close(self):
        pass


async def wait_until(check):
    async with asyncio.timeout(1):
        while not check():  # noqa: ASYNC110 -- bounded polling of a cross-thread fake serial sink
            await asyncio.sleep(0.005)


async def test_idle_reader_records_all_urcs_unknowns_and_preserves_release_before_cleanup():
    port = Port()
    modem = Sim7600Modem("fake", serial_factory=lambda *a, **kw: port)
    events = []
    await modem.open()
    await modem.start_monitoring(events.append)
    try:
        for line in [b'+NEW_EVENT: "private-name",+15551234567\r\n', b"BUSY\r\n", b"BUSY\r\n"]:
            port.lines.put(line)
        await wait_until(lambda: sum(e["signal"] == "BUSY" for e in events) == 2)
        assert "+NEW_EVENT" in str(events)
        assert "private-name" not in str(events) and "15551234567" not in str(events)
        first = await modem.capture_release()
        assert first["reason"] == "busy"
        assert port.commands.index("AT+CEER") < port.commands.index("AT+CREG?")
        port.report = b"+CEER: Normal call clearing\r\n"
        await modem.hangup()
        assert await modem.capture_release() == first
    finally:
        await modem.close()
    assert modem._monitor_task is None


async def test_monitor_and_command_have_single_serial_reader():
    port = Port()
    port.active = True
    modem = Sim7600Modem("fake", serial_factory=lambda *a, **kw: port)
    await modem.open()
    await modem.start_monitoring(lambda _: None)
    try:
        results = await asyncio.gather(*(modem.state() for _ in range(10)))
        assert results == [CallState.ACTIVE] * 10
    finally:
        await modem.close()


async def test_busy_call_never_enters_conversation_and_updates_shared_termination():
    port = Port()
    modem = Sim7600Modem("fake", serial_factory=lambda *a, **kw: port)
    host = SimpleNamespace(termination=CallTermination(), converse=AsyncMock())
    driver = Sim7600CallDriver(host)
    driver.modem, driver.tracker = modem, Mock()

    async def busy(_):
        modem._handle_unsolicited("BUSY", "urc")
        raise RuntimeError("ended before answer")

    driver.session = SimpleNamespace(start_call=busy)
    result = await driver.call("+15551234567")
    assert result["termination"]["cause"] == "busy"
    assert host.termination.summary.cause == "busy"
    host.converse.assert_not_awaited()
    await modem.close()


async def test_connection_deadline_does_not_claim_carrier_no_answer():
    host = SimpleNamespace(termination=CallTermination(), converse=AsyncMock())
    driver = Sim7600CallDriver(host)
    driver.session = SimpleNamespace(
        start_call=AsyncMock(side_effect=Sim7600ConnectionTimeout(90, CallState.DIALING))
    )
    result = await driver.call("+15551234567")
    assert result["termination"]["cause"] == "connection_timeout"
    host.converse.assert_not_awaited()


async def test_failed_release_capture_does_not_skip_release_verification():
    modem = Sim7600Modem("fake")
    host = SimpleNamespace(close=AsyncMock())
    driver = Sim7600CallDriver(host)
    driver.modem, driver.tracker, driver.dial_attempted = modem, Mock(), True
    driver.session = SimpleNamespace(end_call=AsyncMock())
    driver._capture_outcome = AsyncMock(side_effect=RuntimeError("fake evidence failure"))
    driver._verify_release = AsyncMock(return_value=(True, CallState.IDLE, None))
    result = await driver.close()
    assert result["release_confirmed"]
    driver._verify_release.assert_awaited_once()


async def test_prepare_failure_does_not_capture_a_previous_calls_release():
    driver = Sim7600CallDriver(SimpleNamespace(close=AsyncMock()))
    driver.modem = Sim7600Modem("fake")
    driver._capture_outcome = AsyncMock()
    driver._verify_release = AsyncMock(return_value=(True, CallState.IDLE, None))
    await driver.close()
    driver._capture_outcome.assert_not_awaited()


def detector():
    host = SimpleNamespace(
        termination=CallTermination(),
        tracker=Mock(),
        worker=SimpleNamespace(cancel=AsyncMock()),
        _call_hung_up=False,
    )
    result = AnswerDetection(
        host, FrameProcessor(), timeout_seconds=0.01, provider="fake", model="fake"
    )
    result.detector._conversation_notifier.notify = AsyncMock()
    result.detector._gate_notifier.notify = AsyncMock()
    return result


async def test_voicemail_is_model_evidence_and_cancels_worker_without_gate_end_frame():
    detection = detector()
    await detection.voicemail()
    await detection.host._end_task
    assert detection.host.termination.summary.cause == "voicemail"
    assert detection.host.termination.summary.answer_detection["confidence"] == "model_assessed"
    detection.host.worker.cancel.assert_awaited_once()


async def test_timeout_is_unknown_releases_gate_and_ignores_late_voicemail():
    detection = detector()
    detection.start()
    await detection.timer
    assert detection.state == "unknown_timeout"
    detection.detector._conversation_notifier.notify.assert_awaited_once()
    await detection.voicemail()
    detection.host.worker.cancel.assert_not_awaited()
    assert detection.host.termination.summary.cause == "unknown"
    await detection.close()


async def test_human_detection_does_not_trigger_timeout_or_voicemail_hangup():
    detection = detector()
    await detection.human()
    await detection.fail_open()
    await detection.voicemail()
    assert detection.state == "human"
    detection.host.worker.cancel.assert_not_awaited()


def test_plain_and_unknown_numeric_urcs_during_a_command_are_retained():
    modem = Sim7600Modem("fake")
    modem._handle_unsolicited("SMS Ready", "command", "AT+CLCC")
    modem._handle_unsolicited("+FUTURE_END: 1,32,0,16", "command", "AT+CLCC")
    assert len(modem._events) == 2
    assert "+FUTURE_END:1,32,0,16" in modem._events[1]["signal"]
    assert modem._events[0]["payload_bytes"] > 0


async def test_failed_detection_releases_gate_without_failing_main_pipeline():
    from pathlib import Path

    from pipecat.frames.frames import ErrorFrame
    from voice_runtime.execution.native import NativePipelineHost
    from voice_runtime.execution.voicemail import AnswerDetectionObserver

    detection = detector()
    frame = ErrorFrame(error="fake classification failure")
    observer = AnswerDetectionObserver(detection)
    await observer.on_push_frame(SimpleNamespace(source=detection.llm, frame=frame))
    assert detection.state == "unknown_classifier_error"
    host = NativePipelineHost("fake", Path("unused"), SimpleNamespace())
    host.answer_detection = detection
    await host._pipeline_failed(frame)
    assert host.termination.summary.cause == "unknown"


def test_voicemail_configuration_defaults_and_bounds():
    from pydantic import ValidationError
    from voice_runtime.contracts.providers import CallLimits

    assert CallLimits().voicemail_detection_enabled
    for value in (float("inf"), float("nan"), 0, 31):
        with pytest.raises(ValidationError):
            CallLimits(voicemail_detection_timeout_secs=value)
