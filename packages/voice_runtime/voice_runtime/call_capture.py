"""Safe operational events and timestamp-aligned serial PCM recordings."""

import time
import wave
from collections import Counter
from pathlib import Path

import numpy as np
from pipecat.observers.base_observer import BaseObserver, FramePushed

from voice_runtime.perf_diagnostics import is_enabled, timing
from voice_runtime.safe_logs import RuntimeEvent, operational_event


class CallCapture(BaseObserver):
    def __init__(self, directory: Path, sample_rate: int = 8000, clock=time.monotonic):
        super().__init__()
        directory.mkdir(parents=True, exist_ok=True)
        self.directory = directory
        self.sample_rate = sample_rate
        self.clock = clock
        self.started = clock()
        self.frames = Counter()
        self.pcm_bytes = Counter()
        self.positions = {"input": 0, "output": 0}
        self.files = {}
        self.closed = False
        self._has_direct_pcm = False
        self._last_pcm_at = {"input": None, "output": None}
        for name in self.positions:
            wav = wave.open(str(directory / f"{name}.wav"), "wb")
            wav.setparams((1, 2, sample_rate, 0, "NONE", "not compressed"))
            wav.writeframes(b"")
            self.files[name] = wav

    def pcm(self, direction: str, audio: bytes, *, direct: bool = True):
        """RX is timestamped at read completion; TX at successful write completion."""
        started = time.perf_counter() if is_enabled() else 0
        if started:
            previous = self._last_pcm_at[direction]
            if previous is not None:
                gap_ms = (started - previous) * 1000
                expected_ms = len(audio) / (self.sample_rate * 2) * 1000
                if gap_ms >= expected_ms + 40:
                    timing("capture" if direct else "browser_audio", "gap", gap_ms)
            self._last_pcm_at[direction] = started
        if direct:
            self._has_direct_pcm = True
        if len(audio) % 2:
            audio = audio[:-1]
        samples = len(audio) // 2
        observed = round((self.clock() - self.started) * self.sample_rate)
        if direction == "input":
            observed -= samples
        start = max(self.positions[direction], observed, 0)
        gap = start - self.positions[direction]
        self.files[direction].writeframes(b"\0\0" * gap + audio)
        if started:
            elapsed_ms = (time.perf_counter() - started) * 1000
            if elapsed_ms >= 10:
                timing("capture", "frame", elapsed_ms)
        self.positions[direction] = start + samples
        self.pcm_bytes[direction] += len(audio)
        count = self.pcm_bytes[direction]
        if count == len(audio) or count // 16000 != (count - len(audio)) // 16000:
            operational_event(
                RuntimeEvent.PCM_CAPTURED, direction=direction, bytes=count, samples=samples
            )

    async def on_push_frame(self, data: FramePushed):
        frame = data.frame
        edge = (data.source.name, data.destination.name, type(frame).__name__)
        self.frames[edge] += 1
        count = self.frames[edge]
        audio = getattr(frame, "audio", None)

        if not self._has_direct_pcm and audio:
            from pipecat.frames.frames import InputAudioRawFrame, OutputAudioRawFrame
            from pipecat.transports.base_input import BaseInputTransport
            from pipecat.transports.base_output import BaseOutputTransport

            if isinstance(frame, InputAudioRawFrame) and isinstance(
                data.source, BaseInputTransport
            ):
                self.pcm("input", audio, direct=False)
            elif isinstance(frame, OutputAudioRawFrame) and isinstance(
                data.destination, BaseOutputTransport
            ):
                self.pcm("output", audio, direct=False)

        if audio is not None and count != 1 and count % 50:
            return
        operational_event(RuntimeEvent.FRAME_OBSERVED, level="DEBUG", count=count)

    def close(self):
        if self.closed:
            return
        self.closed = True
        end = max(*self.positions.values(), round((self.clock() - self.started) * self.sample_rate))
        for name, wav in self.files.items():
            wav.writeframes(b"\0\0" * (end - self.positions[name]))
            wav.close()
        with (
            wave.open(str(self.directory / "input.wav"), "rb") as user,
            wave.open(str(self.directory / "output.wav"), "rb") as agent,
            wave.open(str(self.directory / "mixed.wav"), "wb") as mixed,
        ):
            mixed.setparams(user.getparams())
            while left := user.readframes(8000):
                right = agent.readframes(8000)
                values = np.frombuffer(left, "<i2").astype(np.int32) + np.frombuffer(
                    right, "<i2"
                ).astype(np.int32)
                mixed.writeframes(np.clip(values, -32768, 32767).astype("<i2").tobytes())
        operational_event(
            RuntimeEvent.CAPTURE_CLOSED,
            bytes=sum(self.pcm_bytes.values()),
            count=sum(self.frames.values()),
            duration_ms=(self.clock() - self.started) * 1000,
        )
