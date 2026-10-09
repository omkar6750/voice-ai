from unittest.mock import AsyncMock

import pytest
import voice_runtime.telephony.driver as driver_module
from voice_runtime.telephony.base import CallState
from voice_runtime.telephony.driver import Sim7600CallDriver
from voice_runtime.telephony.session import TelephonySession


class Clock:
    now = 0.0

    async def sleep(self, seconds):
        self.now += seconds

    def monotonic(self):
        return self.now


class Modem:
    def __init__(self, states, fallback):
        self.states = iter(states)
        self.fallback = fallback
        self.hangup = AsyncMock()
        self.close = AsyncMock()

    async def state(self):
        return next(self.states, self.fallback)


@pytest.mark.asyncio
async def test_late_call_is_hung_up_again_before_stable_release(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(driver_module, "monotonic", clock.monotonic, raising=False)
    monkeypatch.setattr(driver_module, "sleep", clock.sleep, raising=False)
    modem = Modem([CallState.IDLE, CallState.IDLE, CallState.ACTIVE], CallState.IDLE)
    host = type("Host", (), {"close": AsyncMock()})()
    driver = Sim7600CallDriver(host, release_timeout=10, release_stable_secs=5)
    driver.modem = modem
    driver.session = TelephonySession(modem)
    driver.dial_attempted = True
    result = await driver.close()
    assert result["release_confirmed"]
    assert modem.hangup.await_count == 2
    assert clock.now >= 7
    modem.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_persistent_call_is_uncertain_despite_successful_hangup_command(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(driver_module, "monotonic", clock.monotonic, raising=False)
    monkeypatch.setattr(driver_module, "sleep", clock.sleep, raising=False)
    modem = Modem([], CallState.DIALING)
    driver = Sim7600CallDriver(
        type("Host", (), {"close": AsyncMock()})(), release_timeout=5, release_stable_secs=3
    )
    driver.modem = modem
    driver.session = TelephonySession(modem)
    driver.dial_attempted = True
    result = await driver.close()
    assert not result["release_confirmed"]
    assert result["modem_state"] == "dialing"
    assert modem.hangup.await_count >= 2
    assert clock.now <= 5


@pytest.mark.asyncio
async def test_call_connection_timeout_has_last_state_and_does_not_start_audio():
    from voice_runtime.telephony.session import Sim7600ConnectionTimeout

    modem = Modem([], CallState.DIALING)
    modem.dial = AsyncMock()
    modem.start_usb_audio = AsyncMock()
    with pytest.raises(Sim7600ConnectionTimeout) as error:
        await TelephonySession(modem, connect_timeout=0.001).start_call("+15551234567")
    assert error.value.last_state == CallState.DIALING
    modem.start_usb_audio.assert_not_awaited()


@pytest.mark.asyncio
async def test_runtime_persists_connection_timeout_as_run_diagnostic():
    from types import SimpleNamespace
    from unittest.mock import Mock, patch

    from voice_runner.session import Session
    from voice_runtime.telephony.session import Sim7600ConnectionTimeout

    error = Sim7600ConnectionTimeout(90, CallState.DIALING)
    driver = SimpleNamespace(prepare=AsyncMock(), call=AsyncMock(side_effect=error))
    tracker = SimpleNamespace(request_attempt=Mock(), diagnostic=Mock())
    obj = SimpleNamespace(
        run_id="test-run",
        trace=None,
        tracker=tracker,
        make_host=Mock(),
        finish=AsyncMock(),
        termination=SimpleNamespace(request=Mock()),
        request=SimpleNamespace(channel="sim7600", snapshot={}, destination="+15551234567"),
        manager=SimpleNamespace(
            settings=SimpleNamespace(
                call_max_duration_seconds=600,
                sim7600_connect_timeout_seconds=90,
                sim7600_release_timeout_seconds=30,
                sim7600_release_stable_seconds=15,
            )
        ),
    )
    with patch("voice_runtime.telephony.driver.Sim7600CallDriver", return_value=driver):
        await Session.run_pipeline(obj)
    diagnostic = tracker.diagnostic.call_args.kwargs
    assert diagnostic["code"] == "sim7600_connect_timeout"
    assert diagnostic["metadata"] == {"timeout_seconds": 90, "last_call_state": "dialing"}
    obj.finish.assert_awaited_once()


def test_release_stability_must_fit_within_runtime_deadline():
    from voice_runner.settings import RuntimeSettings

    with pytest.raises(ValueError, match="deadline must exceed"):
        RuntimeSettings(sim7600_release_timeout_seconds=10, sim7600_release_stable_seconds=15)
