from unittest.mock import AsyncMock

import pytest
from voice_runtime.telephony.base import CallState
from voice_runtime.telephony.session import TelephonySession
from voice_runtime.telephony.sim7600 import ModemCommandError, Sim7600Modem


@pytest.mark.asyncio
async def test_pcm_registration_only_after_answer():
    modem = AsyncMock()
    modem.state.return_value = CallState.ACTIVE
    await TelephonySession(modem).start_call("+15551234567")
    assert [call[0] for call in modem.mock_calls] == ["dial", "state", "start_usb_audio"]


@pytest.mark.asyncio
async def test_at_waits_across_empty_reads_and_fragmented_lines():
    class Port:
        def write(self, data):
            self.lines = iter([b"", b"\r\n", b"+CPCM", b"REG: 1\r\n", b"O", b"K\r\n"])

        def readline(self):
            return next(self.lines)

    modem = Sim7600Modem("fake", serial_factory=lambda *a, **kw: Port())
    await modem.open()
    assert await modem._command("AT+CPCMREG?") == ["+CPCMREG: 1", "OK"]


@pytest.mark.asyncio
async def test_hangup_still_runs_when_audio_stop_fails():
    modem = AsyncMock()
    modem.stop_usb_audio.side_effect = ModemCommandError("audio stop failed")
    session = TelephonySession(modem)
    session._audio_started = True
    with pytest.raises(ModemCommandError):
        await session.end_call()
    modem.hangup.assert_awaited_once()


@pytest.mark.asyncio
async def test_missing_at_response_is_not_assumed_success():
    class Port:
        def write(self, data):
            pass

        def readline(self):
            return b""

    modem = Sim7600Modem("fake", serial_factory=lambda *a, **kw: Port(), command_timeout=0.01)
    await modem.open()
    with pytest.raises(ModemCommandError, match="timed out"):
        await modem.start_usb_audio()
