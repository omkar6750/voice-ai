"""One media-stream close owner: playback acknowledgement, then verified hangup.

Twilio marks returned after clear are not playback confirmations. Pipeline and
carrier completion are independent; no network write is automatically retried.
"""

from __future__ import annotations

import asyncio
import json
import math
from collections.abc import Awaitable, Callable
from uuid import uuid4

from pipecat.frames.frames import CancelFrame, EndFrame, Frame, InterruptionFrame
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.transports.base_input import BaseInputTransport
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketInputTransport,
    FastAPIWebsocketTransport,
)

from voice_runtime.contracts.diagnostics import diagnostic_dict
from voice_runtime.execution.termination import CallTermination
from voice_runtime.telephony.twilio_rest import TwilioRestCall

TERMINAL_STATUSES = frozenset({"completed", "busy", "failed", "no-answer", "canceled"})


class TwilioMediaSession:
    def __init__(
        self,
        stream_sid: str,
        termination: CallTermination,
        send: Callable[[dict], Awaitable[None]],
        rest: TwilioRestCall,
        *,
        playback_timeout_secs: float = 4,
    ) -> None:
        if not math.isfinite(playback_timeout_secs) or playback_timeout_secs <= 0:
            raise ValueError("Playback timeout must be finite and positive")
        self.stream_sid = stream_sid
        self.termination = termination
        self.rest = rest
        self.diagnostics: list[dict] = []
        self.provider_status: str | None = None
        self._send = send
        self._timeout = playback_timeout_secs
        self._send_lock = asyncio.Lock()
        self._connected = True
        self._audio_pending = False
        self._mark: str | None = None
        self._mark_returned = False
        self._wake = asyncio.Event()
        self._interrupted = False
        self._hangup_requested = False
        self._close_task: asyncio.Task | None = None

    async def __call__(self) -> bool:
        # Our own REST hangup can disconnect before EndFrame processing returns.
        return self._connected or self._hangup_requested

    def _diagnostic(self, code: str, message: str, *, uncertain: bool = False) -> None:
        self.diagnostics.append(
            diagnostic_dict(
                severity="warning" if uncertain else "info",
                category="call_termination",
                source="transport",
                code=code,
                message=message,
                uncertain=uncertain,
            )
        )

    def disconnected(self) -> None:
        self._connected = False
        if not self._hangup_requested:
            self.termination.request("disconnect_unknown")
            self.interrupted()

    def interrupted(self) -> None:
        self._mark = None
        self._audio_pending = False
        self._interrupted = True
        self.termination.playback_interrupted()
        if self.termination.closing and self.termination.summary.mode == "graceful":
            self.termination.request("cancelled")
        self._wake.set()

    def acknowledge(self, name: str) -> None:
        if name == self._mark and not self._interrupted:
            self._mark_returned = True
            self._wake.set()

    async def send_payload(self, payload: dict) -> None:
        async with self._send_lock:
            event = payload.get("event")
            if event == "clear":
                self.interrupted()
            if event == "media" and self._close_task is not None:
                return  # Never append fresh speech behind a final playback mark.
            try:
                async with asyncio.timeout(self._timeout):
                    await self._send(payload)
            except Exception:
                self.termination.request("network_failure")
                self.disconnected()
                self._diagnostic("twilio_send_failed", "Twilio stream write failed", uncertain=True)
                raise RuntimeError("Twilio stream write failed") from None
            if event == "media":
                self._audio_pending = True
                self._interrupted = False
                self.termination.playback_started()

    async def close(self, *, graceful: bool = False) -> None:
        if self._close_task is None:
            self._close_task = asyncio.create_task(self._close(graceful))
        elif not graceful and not self._close_task.done():
            self.interrupted()
        # Cancellation of a pipeline waiter must not orphan an uncertain POST.
        await asyncio.shield(self._close_task)

    async def _drain(self) -> None:
        if not self._audio_pending or not self._connected:
            return
        self._wake.clear()
        self._mark_returned = False
        self._mark = f"voice-final-{uuid4().hex}"
        self.termination.playback_started()
        try:
            async with asyncio.timeout(self._timeout):
                await self.send_payload(
                    {"event": "mark", "streamSid": self.stream_sid, "mark": {"name": self._mark}}
                )
                await self._wake.wait()
        except TimeoutError:
            self.termination.request("drain_timeout")
            self._diagnostic(
                "twilio_playback_timeout",
                "Twilio final playback mark was not received",
                uncertain=True,
            )
        if self._mark_returned and not self._interrupted:
            self.termination.summary.playback_status = "drained"
            self.termination.summary.playback_source = "twilio_mark"
            self._audio_pending = False
        else:
            self.termination.summary.playback_status = "interrupted"

    async def _close(self, graceful: bool) -> None:
        try:
            if graceful:
                try:
                    await self._drain()
                except Exception:
                    self._diagnostic(
                        "twilio_drain_failed", "Twilio playback drain failed", uncertain=True
                    )
            else:
                self.interrupted()
            self._hangup_requested = True
            try:
                await self.rest.complete()
            except Exception:
                # The POST may have succeeded remotely. Resolve by reading, not retrying.
                self._diagnostic(
                    "twilio_hangup_write_uncertain",
                    "Twilio hangup write was not confirmed",
                    uncertain=True,
                )
            try:
                self.provider_status = await self.rest.status()
            except Exception:
                self.provider_status = None
            confirmed = self.provider_status in TERMINAL_STATUSES
            self.termination.summary.cleanup_status = "confirmed" if confirmed else "uncertain"
            if not confirmed:
                self._diagnostic(
                    "twilio_hangup_uncertain",
                    "Twilio call release was not confirmed",
                    uncertain=True,
                )
        finally:
            try:
                await self.rest.aclose()
            except Exception:
                self._diagnostic(
                    "twilio_rest_cleanup_failed",
                    "Twilio REST client cleanup failed",
                    uncertain=True,
                )


class ManagedTwilioSerializer(TwilioFrameSerializer):
    """Keep Pipecat's codecs; own media writes and observe protocol close facts."""

    def __init__(self, session: TwilioMediaSession, *, sample_rate: int) -> None:
        super().__init__(
            stream_sid=session.stream_sid,
            params=self.InputParams(
                sample_rate=sample_rate, twilio_sample_rate=8000, auto_hang_up=False
            ),
        )
        self.session = session

    async def serialize(self, frame: Frame) -> str | bytes | None:
        if isinstance(frame, (EndFrame, CancelFrame)):
            await self.session.close(graceful=isinstance(frame, EndFrame))
            return None
        if isinstance(frame, InterruptionFrame):
            self.session.interrupted()
        payload = await super().serialize(frame)
        if payload:
            await self.session.send_payload(json.loads(payload))
        return None

    async def deserialize(self, data: str | bytes) -> Frame | None:
        try:
            message = json.loads(data)
        except (ValueError, UnicodeDecodeError):
            self.session.termination.request("network_failure")
            self.session.disconnected()
            raise ValueError("Twilio message is malformed") from None
        if not isinstance(message, dict) or message.get("streamSid") != self.session.stream_sid:
            self.session.termination.request("network_failure")
            self.session.disconnected()
            raise ValueError("Twilio message has invalid stream identity")
        if message.get("event") == "mark":
            mark = message.get("mark")
            if isinstance(mark, dict) and isinstance(mark.get("name"), str):
                self.session.acknowledge(mark["name"])
            return None
        if message.get("event") == "stop":
            self.session.disconnected()
            return None
        return await super().deserialize(data)


class _DrainAwareInput(FastAPIWebsocketInputTransport):
    async def stop(self, frame: EndFrame) -> None:
        # Pipecat 1.11.0's stock stop tears down the shared socket/reader before
        # output.stop can drain audio and await its final Twilio mark. Stop input
        # audio here, but retain the reader until output.stop/cleanup disconnects.
        await BaseInputTransport.stop(self, frame)


class ManagedTwilioTransport(FastAPIWebsocketTransport):
    """Pipecat's transport/codecs with a reader alive through graceful drain.

    The input replacement uses pinned Pipecat 1.11.0 internals. Contract tests
    exercise real input/output shutdown; review this adapter on SDK upgrades.
    Cancellation retains stock immediate teardown; the session finally owns REST
    hangup even when the output serializer cannot run on a disconnected socket.
    """

    def __init__(self, websocket, params):
        super().__init__(websocket, params)
        self._input = _DrainAwareInput(self, self._client, self._params, name=self._input_name)
