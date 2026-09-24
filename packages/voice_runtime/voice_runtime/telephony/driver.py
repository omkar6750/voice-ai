"""SIM7600 call driver: pipeline host owns Pipecat, this adapter owns COM control."""

from typing import Protocol

from voice_runtime.execution.exchange import ExchangeTracker
from voice_runtime.telephony.base import CallState
from voice_runtime.telephony.session import TelephonySession
from voice_runtime.telephony.sim7600 import Sim7600Modem


class PipelineHost(Protocol):
    async def prepare(self, snapshot: dict, tracker: ExchangeTracker) -> None:
        """Build/start pipeline and open USB PCM before dialing, without greeting yet."""
        ...

    async def converse(self, modem: Sim7600Modem) -> dict:
        """Trigger greeting after connection; return when conversation ends."""
        ...

    async def close(self) -> None: ...


class Sim7600CallDriver:
    def __init__(self, host: PipelineHost, modem_factory=Sim7600Modem):
        self.host = host
        self.modem_factory = modem_factory
        self.modem = None
        self.session = None
        self.dial_attempted = False

    async def prepare(self, snapshot: dict, tracker: ExchangeTracker) -> None:
        endpoint = snapshot["_resolved"]["endpoint"]
        self.modem = self.modem_factory(
            endpoint["at_port"], endpoint["baudrate"], command_timeout=endpoint["at_timeout_secs"]
        )
        await self.modem.open()
        status = await self.modem.status()
        if not status.can_make_call:
            raise RuntimeError("Modem is not ready for voice calling")
        await self.modem.ensure_pcm_format(snapshot["audio"]["sample_rate"])
        self.session = TelephonySession(self.modem)
        await self.host.prepare(snapshot, tracker)

    async def call(self, destination: str) -> dict:
        self.dial_attempted = True
        await self.session.start_call(destination)
        return await self.host.converse(self.modem)

    async def close(self) -> None:
        try:
            if self.session and self.dial_attempted:
                await self.session.end_call()
                if await self.modem.state() not in (CallState.IDLE, CallState.DISCONNECTED):
                    raise RuntimeError("Modem still reports an active call")
        finally:
            try:
                await self.host.close()
            finally:
                if self.modem:
                    await self.modem.close()
