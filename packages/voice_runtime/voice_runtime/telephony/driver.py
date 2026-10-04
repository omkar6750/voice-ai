"""SIM7600 call driver: pipeline host owns Pipecat, this adapter owns COM control."""

import asyncio
from typing import Protocol

from voice_runtime.diagnostics import modem_status_metadata
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
        self.trace = None

    async def prepare(self, snapshot: dict, tracker: ExchangeTracker) -> None:
        endpoint = snapshot["_resolved"]["endpoint"]
        self.modem = self.modem_factory(
            endpoint["at_port"], endpoint["baudrate"], command_timeout=endpoint["at_timeout_secs"]
        )
        self.modem.trace = self.trace
        await self.modem.open()
        status = await self.modem.status()
        if status.active_call:
            await self.modem.close()
            self.modem = None
            raise RuntimeError("Modem already has an active call; refusing to dial")
        if not status.can_make_call:
            tracker.diagnostic(
                severity="error",
                category="modem_readiness",
                source="modem",
                code="modem_not_ready",
                message="Modem is not ready for voice calling",
                detail=status.last_error,
                metadata=modem_status_metadata(status),
            )
            raise RuntimeError("Modem is not ready for voice calling")
        await self.modem.ensure_pcm_format(snapshot["audio"]["sample_rate"])
        self.session = TelephonySession(self.modem)
        await self.host.prepare(snapshot, tracker)

    async def call(self, destination: str) -> dict:
        self.dial_attempted = True
        await self.session.start_call(destination)
        return await self.host.converse(self.modem)

    async def close(self) -> dict:
        confirmed = False
        final_state = None
        error_category = None
        if self.trace is not None:
            self.trace.record("cleanup_started", component="telephony", source="cleanup")
        try:
            if self.modem:
                try:
                    final_state = await self.modem.state()
                    if self.session and self.dial_attempted:
                        await self.session.end_call()
                    final_state = await self.modem.state()
                    confirmed = final_state in (CallState.IDLE, CallState.DISCONNECTED)
                except Exception as exc:
                    from voice_runtime.safe_logs import error_category as classify

                    error_category = classify(exc)
                    try:
                        final_state = await self.modem.state()
                        confirmed = final_state in (CallState.IDLE, CallState.DISCONNECTED)
                    except Exception:
                        pass
        finally:
            try:
                await asyncio.wait_for(self.host.close(), timeout=10)
            except Exception as exc:
                confirmed = False
                if error_category is None:
                    from voice_runtime.safe_logs import error_category as classify

                    error_category = classify(exc)
            if self.modem:
                try:
                    await self.modem.close()
                except Exception as exc:
                    confirmed = False
                    if error_category is None:
                        from voice_runtime.safe_logs import error_category as classify

                        error_category = classify(exc)
        if self.trace is not None:
            self.trace.record(
                "cleanup_finished",
                component="telephony",
                source="cleanup",
                release_confirmed=confirmed,
                call_state=final_state.value if final_state is not None else "unknown",
                error_category=error_category or "unknown",
            )
        return {
            "release_confirmed": confirmed,
            "modem_state": final_state.value if final_state is not None else "unknown",
            "error_category": error_category,
        }
