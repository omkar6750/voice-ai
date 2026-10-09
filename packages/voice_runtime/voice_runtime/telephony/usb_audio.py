from __future__ import annotations

import asyncio
import math
import os
import struct
import time
from time import perf_counter

import serial
from pipecat.frames.frames import InputAudioRawFrame, OutputAudioRawFrame, StartFrame
from pipecat.processors.frame_processor import FrameProcessor, FrameProcessorSetup
from pipecat.transports.base_input import BaseInputTransport
from pipecat.transports.base_output import BaseOutputTransport
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pydantic import Field

from voice_runtime.perf_diagnostics import is_enabled, timing
from voice_runtime.safe_logs import RuntimeEvent, error_category, operational_event


class Sim7600UsbAudioParams(TransportParams):
    audio_port: str
    baudrate: int = 115200
    audio_frame_ms: int = Field(default=20, ge=10, le=100)
    audio_in_sample_rate: int = 16000
    audio_out_sample_rate: int = 16000


class _SerialPcmOwner:
    def __init__(self, params: Sim7600UsbAudioParams, capture=None, trace=None) -> None:
        self.params = params
        self.capture = capture
        self.trace = trace
        self._serial: serial.Serial | None = None
        self._open_lock = asyncio.Lock()
        self._io_summary: dict[str, dict[str, int | float]] = {}
        self._turn_diag_enabled = (
            os.getenv("VOICE_MODEM_TURN_DIAGNOSTICS", "").strip().lower()
            in {"1", "true", "yes", "on"}
            and trace is not None
        )
        self._turn_window_samples = 0
        self._turn_window_sum_squares = 0
        self._turn_window_peak = 0
        self._turn_window_clipped = 0
        self._turn_window_started: float | None = None

    async def open(self) -> None:
        async with self._open_lock:
            if self._serial is None:
                self._serial = await asyncio.to_thread(
                    serial.Serial,
                    self.params.audio_port,
                    self.params.baudrate,
                    timeout=0.25,
                    write_timeout=2,
                )
                operational_event(RuntimeEvent.PCM_OPENED)

    async def close(self) -> None:
        async with self._open_lock:
            self._flush_turn_pcm()
            self._flush_io_summaries()
            if self._serial is not None:
                await asyncio.to_thread(self._serial.close)
                self._serial = None

    async def read(self, size: int) -> bytes:
        if self._serial is None:
            raise RuntimeError("SIM7600 USB audio port is not open")
        started = perf_counter() if is_enabled() else 0
        payload = await asyncio.to_thread(self._serial.read, size)
        if payload:
            self._record_io("input", payload, self.params.audio_in_sample_rate)
        if started and payload:
            elapsed_ms = (perf_counter() - started) * 1000
            if elapsed_ms >= 30:
                timing("sim_rx", "read", elapsed_ms)
        return payload

    async def write(self, payload: bytes) -> None:
        if self._serial is None:
            raise RuntimeError("SIM7600 USB audio port is not open")
        started = perf_counter() if is_enabled() else 0
        written = await asyncio.to_thread(self._serial.write, payload)
        if started:
            elapsed_ms = (perf_counter() - started) * 1000
            if elapsed_ms >= 20:
                timing("sim_tx", "write", elapsed_ms)
        if written != len(payload):
            raise OSError(f"Short PCM write: {written}/{len(payload)} bytes")
        self._record_io("output", payload, self.params.audio_out_sample_rate)
        started = perf_counter() if is_enabled() else 0
        await asyncio.to_thread(self._serial.flush)
        if started:
            elapsed_ms = (perf_counter() - started) * 1000
            if elapsed_ms >= 20:
                timing("sim_tx", "flush", elapsed_ms)
        if self.capture:
            self.capture.pcm("output", payload)

    def _record_io(self, direction: str, payload: bytes, sample_rate: int) -> None:
        now = time.monotonic()
        stats = self._io_summary.setdefault(
            direction, {"started": now, "bytes": 0, "samples": 0, "count": 0}
        )
        stats["bytes"] = int(stats["bytes"]) + len(payload)
        stats["samples"] = int(stats["samples"]) + len(payload) // 2
        stats["count"] = int(stats["count"]) + 1
        if now - float(stats["started"]) < 5:
            return
        self._emit_io_summary(direction, stats, sample_rate, now)

    def record_turn_pcm(self, payload: bytes) -> None:
        """Record opt-in PCM level windows for local modem turn debugging; never audio."""
        if not self._turn_diag_enabled:
            return
        if len(payload) % 2:
            return
        now = time.monotonic()
        if self._turn_window_started is None:
            self._turn_window_started = now
        for (sample,) in struct.iter_unpack("<h", payload):
            magnitude = abs(sample)
            self._turn_window_sum_squares += sample * sample
            self._turn_window_peak = max(self._turn_window_peak, magnitude)
            self._turn_window_clipped += magnitude >= 32760
            self._turn_window_samples += 1
        if self._turn_window_samples < self.params.audio_in_sample_rate // 4:
            return

        elapsed_ms = max(1.0, (now - self._turn_window_started) * 1000)
        rms = math.sqrt(self._turn_window_sum_squares / self._turn_window_samples)

        def dbfs(level: float) -> float:
            return max(-120.0, 20 * math.log10(max(1, level) / 32768))

        self.trace.record(
            "turn_diag_pcm_window",
            component="sim_rx",
            duration_ms=elapsed_ms,
            rms_dbfs=round(dbfs(rms), 1),
            peak_dbfs=round(dbfs(self._turn_window_peak), 1),
            clipped_samples=self._turn_window_clipped,
            samples=self._turn_window_samples,
        )
        self._turn_window_samples = 0
        self._turn_window_sum_squares = 0
        self._turn_window_peak = 0
        self._turn_window_clipped = 0
        self._turn_window_started = now

    def _flush_turn_pcm(self) -> None:
        if not self._turn_diag_enabled or self._turn_window_samples == 0:
            return
        elapsed_ms = max(1.0, (time.monotonic() - self._turn_window_started) * 1000)
        rms = math.sqrt(self._turn_window_sum_squares / self._turn_window_samples)

        def dbfs(level: float) -> float:
            return max(-120.0, 20 * math.log10(max(1, level) / 32768))

        self.trace.record(
            "turn_diag_pcm_window",
            component="sim_rx",
            duration_ms=elapsed_ms,
            rms_dbfs=round(dbfs(rms), 1),
            peak_dbfs=round(dbfs(self._turn_window_peak), 1),
            clipped_samples=self._turn_window_clipped,
            samples=self._turn_window_samples,
        )
        self._turn_window_samples = 0
        self._turn_window_sum_squares = 0
        self._turn_window_peak = 0
        self._turn_window_clipped = 0
        self._turn_window_started = None

    def _flush_io_summaries(self) -> None:
        now = time.monotonic()
        for direction, stats in self._io_summary.items():
            if int(stats["count"]) == 0:
                continue
            rate = (
                self.params.audio_in_sample_rate
                if direction == "input"
                else self.params.audio_out_sample_rate
            )
            self._emit_io_summary(direction, stats, rate, now)

    def _emit_io_summary(
        self, direction: str, stats: dict[str, int | float], sample_rate: int, now: float
    ) -> None:
        component = "sim_rx" if direction == "input" else "sim_tx"
        operational_event(
            RuntimeEvent.PCM_IO_SUMMARY,
            component=component,
            direction=direction,
            phase="read" if direction == "input" else "write",
            bytes=int(stats["bytes"]),
            samples=int(stats["samples"]),
            count=int(stats["count"]),
            sample_rate=sample_rate,
        )
        stats.update(started=now, bytes=0, samples=0, count=0)


class _Sim7600AudioInput(BaseInputTransport):
    def __init__(self, owner: _SerialPcmOwner, params: Sim7600UsbAudioParams) -> None:
        super().__init__(params)
        self._owner = owner
        self._params = params
        self._sample_rate = params.audio_in_sample_rate
        self._task: asyncio.Task[None] | None = None
        self._frame_bytes = 0
        self._last_frame_at: float | None = None

    async def setup(self, setup: FrameProcessorSetup) -> None:
        await super().setup(setup)
        await self._owner.open()
        self._frame_bytes = (
            int(self.sample_rate * self._params.audio_frame_ms / 1000)
            * self._params.audio_in_channels
            * 2
        )

    async def start(self, frame: StartFrame) -> None:
        await super().start(frame)
        self._task = asyncio.create_task(self._read_loop(), name="sim7600-usb-audio-reader")
        await self.set_transport_ready(frame)

    async def cleanup(self) -> None:
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
        await super().cleanup()

    async def _read_loop(self) -> None:
        buffer = bytearray()
        try:
            while True:
                chunk = await self._owner.read(self._frame_bytes - len(buffer))
                if not chunk:
                    continue
                buffer.extend(chunk)
                if len(buffer) < self._frame_bytes:
                    continue
                frame = InputAudioRawFrame(
                    audio=bytes(buffer[: self._frame_bytes]),
                    sample_rate=self.sample_rate,
                    num_channels=1,
                )
                buffer = buffer[self._frame_bytes :]
                self._owner.record_turn_pcm(frame.audio)
                if is_enabled():
                    now = perf_counter()
                    if self._last_frame_at is not None:
                        gap_ms = (now - self._last_frame_at) * 1000
                        if gap_ms >= self._params.audio_frame_ms + 40:
                            timing("sim_rx", "gap", gap_ms)
                    self._last_frame_at = now
                if self._owner.capture:
                    self._owner.capture.pcm("input", frame.audio)
                await self.push_audio_frame(frame)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            if self._owner.trace is not None:
                self._owner.trace.record(
                    "pcm_transport_failure",
                    component="transport",
                    error_category=error_category(exc),
                    processor="input",
                    event_source="pipeline",
                )
            operational_event(
                RuntimeEvent.PCM_READ_FAILED,
                level="ERROR",
                error_category=error_category(exc),
                component="sim_rx",
            )
            await self.push_error("PCM read failed", fatal=True)


class _Sim7600AudioOutput(BaseOutputTransport):
    def __init__(self, owner: _SerialPcmOwner, params: Sim7600UsbAudioParams) -> None:
        super().__init__(params)
        self._owner = owner
        self._params = params
        self._sample_rate = params.audio_out_sample_rate
        self._last_chunk_at: float | None = None

    async def setup(self, setup: FrameProcessorSetup) -> None:
        await super().setup(setup)
        await self._owner.open()

    async def start(self, frame: StartFrame) -> None:
        await super().start(frame)
        await self.set_transport_ready(frame)

    async def cleanup(self) -> None:
        try:
            await super().cleanup()
        finally:
            await self._owner.close()

    async def write_audio_frame(self, frame: OutputAudioRawFrame) -> bool:
        if frame.sample_rate != self.sample_rate or frame.num_channels != 1 or len(frame.audio) % 2:
            khz = (
                f"{self.sample_rate // 1000} kHz"
                if self.sample_rate % 1000 == 0
                else f"{self.sample_rate} Hz"
            )
            raise ValueError(f"Modem output requires {khz} mono signed 16-bit PCM")
        # USB serial writes return immediately; the modem needs realtime 20 ms pacing.
        chunk_bytes = self.sample_rate * self._params.audio_frame_ms // 1000 * 2
        for offset in range(0, len(frame.audio), chunk_bytes):
            chunk = frame.audio[offset : offset + chunk_bytes]
            started = asyncio.get_running_loop().time()
            if is_enabled():
                if self._last_chunk_at is not None:
                    gap_ms = (started - self._last_chunk_at) * 1000
                    if gap_ms >= self._params.audio_frame_ms + 40:
                        timing("sim_tx", "gap", gap_ms)
                self._last_chunk_at = started
            try:
                await self._owner.write(chunk)
            except Exception as exc:
                if self._owner.trace is not None:
                    self._owner.trace.record(
                        "pcm_transport_failure",
                        component="transport",
                        error_category=error_category(exc),
                        processor="output",
                        event_source="pipeline",
                    )
                operational_event(
                    RuntimeEvent.PCM_WRITE_FAILED,
                    level="ERROR",
                    error_category=error_category(exc),
                    component="sim_tx",
                    bytes=len(chunk),
                    samples=len(chunk) // 2,
                )
                await self.push_error("PCM write failed", fatal=True)
                return False
            elapsed = asyncio.get_running_loop().time() - started
            await asyncio.sleep(max(0, len(chunk) / (self.sample_rate * 2) - elapsed))
        return True


class Sim7600UsbAudioTransport(BaseTransport):
    """Pipecat transport for SIM7600 COM-port USB PCM audio."""

    def __init__(self, params: Sim7600UsbAudioParams, capture=None, trace=None) -> None:
        super().__init__()
        self._params = params
        self._owner = _SerialPcmOwner(params, capture, trace)
        self._input: FrameProcessor | None = None
        self._output: FrameProcessor | None = None

    def input(self) -> FrameProcessor:
        if self._input is None:
            self._input = _Sim7600AudioInput(self._owner, self._params)
        return self._input

    def output(self) -> FrameProcessor:
        if self._output is None:
            self._output = _Sim7600AudioOutput(self._owner, self._params)
        return self._output


class Sim7600UsbAudioBridge:
    """Maps the SIM7600 COM17 raw PCM stream into Pipecat."""

    def __init__(
        self,
        audio_port: str,
        baudrate: int = 115200,
        sample_rate: int = 16000,
        channels: int = 1,
        capture=None,
        frame_ms: int = 20,
        trace=None,
    ) -> None:
        self.params = Sim7600UsbAudioParams(
            audio_frame_ms=frame_ms,
            audio_port=audio_port,
            baudrate=baudrate,
            audio_in_sample_rate=sample_rate,
            audio_out_sample_rate=sample_rate,
            audio_in_channels=channels,
            audio_out_channels=channels,
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_out_10ms_chunks=2,
        )
        self._transport: Sim7600UsbAudioTransport | None = None
        self.capture = capture
        self.trace = trace

    def transport(self) -> Sim7600UsbAudioTransport:
        if self._transport is None:
            self._transport = Sim7600UsbAudioTransport(self.params, self.capture, self.trace)
        return self._transport
