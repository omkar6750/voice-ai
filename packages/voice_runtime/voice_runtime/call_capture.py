"""Plain pipeline logs and timestamp-aligned serial PCM recordings for the POC."""

import time
import wave
from collections import Counter
from pathlib import Path

import numpy as np
from loguru import logger
from pipecat.observers.base_observer import BaseObserver, FramePushed


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
        for name in self.positions:
            wav = wave.open(str(directory / f"{name}.wav"), "wb")
            wav.setparams((1, 2, sample_rate, 0, "NONE", "not compressed"))
            wav.writeframes(b"")
            self.files[name] = wav

    def pcm(self, direction: str, audio: bytes):
        """RX is timestamped at read completion; TX at successful write completion."""
        if len(audio) % 2:
            raise ValueError("PCM must contain whole signed 16-bit samples")
        samples = len(audio) // 2
        observed = round((self.clock() - self.started) * self.sample_rate)
        if direction == "input":
            observed -= samples
        start = max(self.positions[direction], observed, 0)
        gap = start - self.positions[direction]
        self.files[direction].writeframes(b"\0\0" * gap + audio)
        self.positions[direction] = start + samples
        self.pcm_bytes[direction] += len(audio)
        count = self.pcm_bytes[direction]
        if count == len(audio) or count // 16000 != (count - len(audio)) // 16000:
            values = np.frombuffer(audio, dtype="<i2").astype(np.float64)
            rms = float(np.sqrt(np.mean(values * values))) if samples else 0.0
            logger.info("PCM {} bytes={} samples={} rms={:.1f}", direction, count, samples, rms)

    async def on_push_frame(self, data: FramePushed):
        frame = data.frame
        edge = (data.source.name, data.destination.name, type(frame).__name__)
        self.frames[edge] += 1
        count = self.frames[edge]
        audio = getattr(frame, "audio", None)
        if audio is not None and count != 1 and count % 50:
            return
        detail = (
            f"bytes={len(audio)} rate={frame.sample_rate} channels={frame.num_channels}"
            if audio is not None
            else getattr(frame, "text", getattr(frame, "error", ""))
        )
        logger.debug(
            "PIPE {} -> {} {} {} count={} {}",
            *edge[:2],
            data.direction.name,
            edge[2],
            count,
            detail,
        )

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
        logger.info("CAPTURE serial bytes={}", dict(self.pcm_bytes))
        logger.debug("CAPTURE frame counts={}", dict(self.frames))
