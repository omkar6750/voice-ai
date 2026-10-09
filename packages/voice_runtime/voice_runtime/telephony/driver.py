"""SIM7600 call driver: pipeline host owns Pipecat, this adapter owns COM control."""

import asyncio
import math
from asyncio import sleep
from time import monotonic
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
    def __init__(
        self,
        host: PipelineHost,
        modem_factory=Sim7600Modem,
        *,
        connect_timeout=90.0,
        release_timeout=30.0,
        release_stable_secs=15.0,
    ):
        if (
            not all(
                math.isfinite(v) and v > 0
                for v in (connect_timeout, release_timeout, release_stable_secs)
            )
            or release_stable_secs > release_timeout
        ):
            raise ValueError(
                "SIM7600 timeouts must be finite and positive; release stability must fit within its deadline"
            )
        self.connect_timeout = connect_timeout
        self.release_timeout = release_timeout
        self.release_stable_secs = release_stable_secs
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
        self.session = TelephonySession(self.modem, connect_timeout=self.connect_timeout)
        await self.host.prepare(snapshot, tracker)

    async def call(self, destination: str) -> dict:
        self.dial_attempted = True
        await self.session.start_call(destination)
        return await self.host.converse(self.modem)

    async def _verify_release(self):
        """Keep ownership until idle stays stable; cancel calls that appear late."""
        from voice_runtime.safe_logs import error_category as classify

        deadline = monotonic() + self.release_timeout
        idle_since = None
        final_state = None
        error = None
        last_hangup = monotonic()
        was_idle = True
        while monotonic() < deadline:
            try:
                async with asyncio.timeout(max(0.001, deadline - monotonic())):
                    final_state = await self.modem.state()
                    if final_state in (CallState.IDLE, CallState.DISCONNECTED):
                        if idle_since is None:
                            idle_since = monotonic()
                        if monotonic() - idle_since >= self.release_stable_secs:
                            return True, final_state, error
                        was_idle = True
                    else:
                        idle_since = None
                        if self.dial_attempted and (was_idle or monotonic() - last_hangup >= 2):
                            await self.modem.hangup()
                            last_hangup = monotonic()
                        was_idle = False
            except Exception as exc:
                idle_since = None
                error = classify(exc)
            remaining = deadline - monotonic()
            if remaining > 0:
                await sleep(min(1.0, self.release_stable_secs / 2, remaining))
        return False, final_state, error or "timeout"

    async def close(self) -> dict:
        confirmed = False
        final_state = None
        error_category = None
        if self.trace is not None:
            self.trace.record("cleanup_started", component="telephony", source="cleanup")
        try:
            if self.modem:
                try:
                    if self.session and self.dial_attempted:
                        # A briefly empty call list must not skip cancellation of an outgoing dial.
                        await self.session.end_call(force=True)
                except Exception as exc:
                    from voice_runtime.safe_logs import error_category as classify

                    error_category = classify(exc)
                confirmed, final_state, verification_error = await self._verify_release()
                error_category = error_category or verification_error
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
