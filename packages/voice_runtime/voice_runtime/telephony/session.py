import asyncio

from voice_runtime.telephony.base import CallState
from voice_runtime.telephony.protocols import Modem


class TelephonySession:
    """Coordinates SIM7600 call control with the Pipecat audio bridge."""

    def __init__(self, modem: Modem, connect_timeout: float = 30.0) -> None:
        self.modem = modem
        self.connect_timeout = connect_timeout
        self._audio_started = False

    async def start_call(self, phone_number: str) -> None:
        # COM audio is already open, but PCM registration requires an active call.
        await self.modem.dial(phone_number)
        deadline = asyncio.get_running_loop().time() + self.connect_timeout
        while asyncio.get_running_loop().time() < deadline:
            state = await self.modem.state()
            if state == CallState.ACTIVE:
                self._audio_started = True
                await self.modem.start_usb_audio()
                return
            if state == CallState.DISCONNECTED:
                raise RuntimeError("call disconnected before becoming active")
            await asyncio.sleep(0.25)
        raise TimeoutError("timed out waiting for SIM7600 call connection")

    async def end_call(self) -> None:
        try:
            state = await self.modem.state()
            if state not in (CallState.IDLE, CallState.DISCONNECTED):
                await self.modem.hangup()
        finally:
            if self._audio_started:
                self._audio_started = False
                await self.modem.stop_usb_audio()

    async def close(self) -> None:
        await self.modem.close()
