from unittest.mock import AsyncMock

import pytest
from voice_runtime.telephony.base import CallState
from voice_runtime.telephony.session import TelephonySession


@pytest.mark.asyncio
async def test_remote_disconnect_skips_redundant_hangup_and_stops_audio() -> None:
    modem = type("FakeModem", (), {})()
    modem.state = AsyncMock(return_value=CallState.DISCONNECTED)
    modem.hangup = AsyncMock()
    modem.stop_usb_audio = AsyncMock()
    session = TelephonySession(modem)
    session._audio_started = True

    await session.end_call()

    modem.hangup.assert_not_awaited()
    modem.stop_usb_audio.assert_awaited_once()


@pytest.mark.asyncio
async def test_driver_host_cleanup_failure_does_not_release_device():
    from voice_runtime.telephony.driver import Sim7600CallDriver

    host = type(
        "Host", (), {"close": AsyncMock(side_effect=RuntimeError("private cleanup failure"))}
    )()
    driver = Sim7600CallDriver(host)
    driver.modem = type(
        "Modem", (), {"state": AsyncMock(return_value=CallState.IDLE), "close": AsyncMock()}
    )()
    result = await driver.close()
    assert not result["release_confirmed"]
    assert "private" not in str(result)
