import pytest
from voice_runtime.telephony.base import CallState
from voice_runtime.telephony.sim7600 import (
    ModemCommandTimeoutError,
    Sim7600Modem,
    redact_at_response,
)
from voice_runtime.telephony.status import ModemStatusReader, parse_call_state


class FakeSerial:
    def __init__(self, *args, **kwargs):
        self.commands: list[str] = []
        self.responses = {
            "AT": [b"OK\r\n"],
            "ATD+15551234567;": [b"OK\r\n"],
            "AT+CHUP": [b"OK\r\n"],
            "AT+CLCC": [b'+CLCC: 1,0,0,0,0,"+15551234567",145\r\n', b"OK\r\n"],
            "AT+CPIN?": [b"+CPIN: READY\r\n", b"OK\r\n"],
            "AT+CSQ": [b"+CSQ: 18,0\r\n", b"OK\r\n"],
            "AT+CEREG?": [b"+CEREG: 0,1\r\n", b"OK\r\n"],
            "AT+CREG?": [b"+CREG: 0,1\r\n", b"OK\r\n"],
            "AT+CGATT?": [b"+CGATT: 1\r\n", b"OK\r\n"],
            "AT+COPS?": [b'+COPS: 0,0,"Example",7\r\n', b"OK\r\n"],
            "AT+CPSI?": [b"+CPSI: LTE,Online,001-01,0,LTE BAND 3,100\r\n", b"OK\r\n"],
            "AT+CGACT?": [b"+CGACT: 1,1\r\n", b"OK\r\n"],
            "AT+CPCMREG?": [b"+CPCMREG: 1\r\n", b"OK\r\n"],
            "ATI": [b"SIM7600\r\n", b"OK\r\n"],
            "AT+CGMR": [b"1.0\r\n", b"OK\r\n"],
            "AT+CEER": [b"+CEER: 0\r\n", b"OK\r\n"],
        }

    def write(self, data: bytes) -> None:
        command = data.decode().strip()
        self.commands.append(command)
        self.current = iter(self.responses[command])

    def readline(self) -> bytes:
        return next(self.current)

    def close(self) -> None:
        pass


@pytest.mark.asyncio
async def test_sim7600_dial_state_and_hangup() -> None:
    fake = FakeSerial()
    modem = Sim7600Modem("COM7", serial_factory=lambda *args, **kwargs: fake)

    await modem.dial("+15551234567")
    assert await modem.state() == CallState.ACTIVE
    await modem.hangup()

    assert fake.commands == ["ATD+15551234567;", "AT+CLCC", "AT+CHUP"]


@pytest.mark.asyncio
async def test_sim7600_status_reports_network_and_audio() -> None:
    fake = FakeSerial()
    modem = Sim7600Modem("COM7", serial_factory=lambda *args, **kwargs: fake)

    fake.responses["AT+CLCC"] = [b"OK\r\n"]
    status = await modem.status()
    assert status.alive is True
    assert status.serial_connected is True
    assert status.sim_ready is True
    assert status.voice_registered is True
    assert status.data_registered is True
    assert status.packet_attached is True
    assert status.can_make_call is True
    assert status.rssi == 18
    assert status.signal_quality == 0
    assert status.operator == "Example"
    assert status.radio_access == "LTE"
    assert status.band == "LTE BAND 3"
    assert status.usb_audio_supported is True
    assert status.usb_audio_active is True
    assert status.available_transports == ("cellular_voice", "lte_data", "usb_audio")


@pytest.mark.parametrize("state", ["4", "5"])
def test_incoming_and_waiting_calls_are_ringing(state: str) -> None:
    lines = [f"+CLCC: 1,1,{state},0,0"]
    assert parse_call_state(lines) == CallState.RINGING


def test_ringing_call_and_unusable_signal_are_not_dial_ready() -> None:
    status = ModemStatusReader().from_results(
        {
            "AT": ["OK"],
            "AT+CPIN?": ["+CPIN: READY", "OK"],
            "AT+CREG?": ["+CREG: 0,1", "OK"],
            "AT+CSQ": ["+CSQ: 0,0", "OK"],
            "AT+CLCC": ["+CLCC: 1,1,4,0,0", "OK"],
        },
        serial_connected=True,
    )
    assert status.call_state == CallState.RINGING
    assert status.active_call is True
    assert status.can_make_call is False


@pytest.mark.asyncio
async def test_invalid_pcm_sample_rate_is_rejected() -> None:
    modem = Sim7600Modem("COM7", serial_factory=lambda *args, **kwargs: FakeSerial())
    with pytest.raises(ValueError, match="8000 or 16000"):
        await modem.ensure_pcm_format(44100)


@pytest.mark.asyncio
async def test_call_state_transition_active_to_idle() -> None:
    fake = FakeSerial()
    modem = Sim7600Modem("COM7", serial_factory=lambda *args, **kwargs: fake)
    await modem.open()
    assert await modem.state() == CallState.ACTIVE
    fake.responses["AT+CLCC"] = [b"OK\r\n"]
    assert await modem.state() == CallState.IDLE


@pytest.mark.asyncio
async def test_no_carrier_during_clcc_is_disconnect_not_command_failure() -> None:
    fake = FakeSerial()
    fake.responses["AT+CLCC"] = [b"NO CARRIER\r\n"]
    modem = Sim7600Modem("COM7", serial_factory=lambda *args, **kwargs: fake)
    assert await modem.state() == CallState.DISCONNECTED


@pytest.mark.asyncio
async def test_modem_trace_never_contains_raw_clcc_response(tmp_path) -> None:
    from uuid import uuid4

    from voice_runtime.execution.local_trace import LocalRuntimeTrace

    fake = FakeSerial()
    trace_path = tmp_path / "modem.jsonl"
    trace = LocalRuntimeTrace(trace_path, str(uuid4()))
    modem = Sim7600Modem("COM7", serial_factory=lambda *args, **kwargs: fake, trace=trace)
    await modem.state()
    trace.close()
    content = trace_path.read_text()
    assert "+15551234567" not in content
    assert "AT+CLCC" in content


@pytest.mark.asyncio
async def test_disconnect_snapshot_is_bounded_and_keeps_per_command_failures() -> None:
    from dataclasses import asdict

    fake = FakeSerial()
    fake.responses["AT+CLCC"] = [b"NO CARRIER\r\n"]
    modem = Sim7600Modem("COM7", serial_factory=lambda *args, **kwargs: fake)
    snapshot = await modem.disconnect_status()
    assert snapshot.call_state == CallState.DISCONNECTED
    assert "AT+CLCC" in fake.commands
    assert "+15551234567" not in str(asdict(snapshot))


@pytest.mark.asyncio
async def test_command_timeout_is_classified_without_response_text() -> None:
    class NoResponseSerial(FakeSerial):
        def write(self, data: bytes) -> None:
            self.commands.append(data.decode().strip())
            self.current = iter(())

        def readline(self) -> bytes:
            return b""

    modem = Sim7600Modem("COM7", serial_factory=lambda *args, **kwargs: NoResponseSerial())
    await modem.open()
    with pytest.raises(ModemCommandTimeoutError):
        await modem._command("AT", timeout_secs=0.01)


@pytest.mark.asyncio
async def test_hangup_rejection_after_remote_disconnect_is_tolerated() -> None:
    fake = FakeSerial()
    fake.responses["AT+CHUP"] = [b"NO CARRIER\r\n"]
    fake.responses["ATH"] = [b"OK\r\n"]
    modem = Sim7600Modem("COM7", serial_factory=lambda *args, **kwargs: fake)
    await modem.hangup()
    assert fake.commands == ["AT+CHUP", "ATH"]


def test_local_trace_allowlist_drops_secrets_and_payloads(tmp_path) -> None:
    import json
    from uuid import uuid4

    from voice_runtime.execution.local_trace import LocalRuntimeTrace

    path = tmp_path / "trace.jsonl"
    trace = LocalRuntimeTrace(path, str(uuid4()))
    trace.record(
        "pipeline_frame",
        component="pipecat",
        frame_type="ErrorFrame",
        processor="tts",
        secret="sensitive transcript",
    )
    trace.close()
    payload = path.read_text()
    assert "sensitive transcript" not in payload
    assert "secret" not in payload
    assert json.loads(payload.splitlines()[1])["frame_type"] == "ErrorFrame"


def test_at_log_redaction_removes_device_and_phone_identifiers() -> None:
    assert redact_at_response("IMEI: 862636055880015") == "IMEI: <redacted>"
    assert redact_at_response("862636055880015") == "<redacted>"
    assert redact_at_response('+CLCC: 1,0,0,0,0,"+15551234567",145').endswith(',"<number>",145')
