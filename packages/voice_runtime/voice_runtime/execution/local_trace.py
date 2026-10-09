"""Local-only, allowlisted diagnostic trace for one development call."""

from __future__ import annotations

import json
import queue
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from voice_shared.dev_visibility import is_development, redact_api_keys

_EVENTS = frozenset(
    {
        "runtime_started",
        "command_started",
        "command_finished",
        "modem_state",
        "call_disconnect_detected",
        "cleanup_started",
        "cleanup_finished",
        "pipeline_frame",
        "pipeline_error",
        "pcm_transport_failure",
        "turn_diag_pcm_window",
        "processor_setup",
        "run_finalized",
    }
)
_COMMANDS = frozenset(
    {
        "AT",
        "ATD",
        "ATA",
        "AT+CHUP",
        "ATH",
        "AT+CLCC",
        "AT+CPIN?",
        "AT+CSQ",
        "AT+CEREG?",
        "AT+CREG?",
        "AT+CGATT?",
        "AT+COPS?",
        "AT+CPSI?",
        "AT+CGACT?",
        "AT+CPCMREG?",
        "AT+CPCMREG=0",
        "AT+CPCMREG=1",
        "AT+CPCMFRM?",
        "AT+CPCMFRM=0",
        "AT+CPCMFRM=1",
        "ATI",
        "AT+CGMR",
        "AT+CEER",
        "other",
    }
)
_STATES = frozenset({"idle", "dialing", "ringing", "active", "disconnected", "unknown"})
_STATUSES = frozenset(
    {"started", "completed", "failed", "cancelled", "interrupted", "timeout", "unknown"}
)
_RESPONSES = frozenset({"ok", "rejected", "data", "no_carrier", "busy", "no_answer", "io"})
_CATEGORIES = frozenset(
    {"timeout", "permission", "connection", "io", "validation", "runtime", "unknown"}
)
_FRAME_TYPES = frozenset(
    {
        "StartFrame",
        "EndFrame",
        "CancelFrame",
        "ErrorFrame",
        "InterruptionFrame",
        "BotStartedSpeakingFrame",
        "BotStoppedSpeakingFrame",
        "TTSStartedFrame",
        "TTSStoppedFrame",
        "LLMFullResponseEndFrame",
        "UserStartedSpeakingFrame",
        "UserStoppedSpeakingFrame",
        "VADUserStartedSpeakingFrame",
        "VADUserStoppedSpeakingFrame",
    }
)
_COMPONENTS = frozenset({"runner", "modem", "telephony", "pipecat", "transport", "api", "sim_rx"})
_PROCESSORS = frozenset({"llm", "stt", "tts", "input", "output", "other"})
_FIELDS = frozenset(
    {
        "command",
        "response",
        "call_state",
        "error_category",
        "frame_type",
        "processor",
        "processor_usable",
        "status",
        "duration_ms",
        "rms_dbfs",
        "peak_dbfs",
        "clipped_samples",
        "samples",
        "sequence",
        "sample_rate",
        "source",
        "release_confirmed",
        "event_source",
    }
)


class LocalRuntimeTrace:
    """Write only fixed event/field names and enum-like values; never raw payloads."""

    def __init__(self, path: Path, run_id: str, on_record=None):
        parsed = UUID(run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.run_id = parsed.hex
        self.started = time.monotonic()
        self.sequence = 0
        self._lock = threading.Lock()
        self._stream = path.open("a", encoding="utf-8")
        self._queue = queue.Queue(maxsize=1024)
        self.dropped = 0
        self._closed = False
        self._on_record = on_record
        self._writer = threading.Thread(target=self._write, name="modem-trace", daemon=True)
        self._writer.start()
        self.record("runtime_started", component="runner")

    def record(self, event: str, *, component: str, **fields) -> None:
        if event not in _EVENTS or component not in _COMPONENTS:
            return
        row = {
            "timestamp": datetime.now(UTC).isoformat(),
            "elapsed_ms": round((time.monotonic() - self.started) * 1000, 3),
            "run_id": self.run_id,
            "event": event,
            "component": component,
        }
        if is_development():
            row.update(redact_api_keys(fields))
        for key, value in ({} if is_development() else fields).items():
            if key not in _FIELDS:
                continue
            if key == "command" and value not in _COMMANDS:
                value = "other"
            elif key == "call_state" and value not in _STATES:
                value = "unknown"
            elif key == "status" and value not in _STATUSES:
                value = "unknown"
            elif key == "response" and value not in _RESPONSES:
                value = "unknown"
            elif key == "error_category" and value not in _CATEGORIES:
                value = "unknown"
            elif key == "frame_type" and value not in _FRAME_TYPES:
                continue
            elif key == "processor" and value not in _PROCESSORS:
                value = "other"
            elif key in {"duration_ms"}:
                if type(value) not in {int, float} or not 0 <= value <= 86_400_000:
                    continue
            elif key in {"rms_dbfs", "peak_dbfs"}:
                if type(value) not in {int, float} or not -120 <= value <= 0:
                    continue
            elif key in {"clipped_samples", "samples"}:
                if type(value) is not int or not 0 <= value <= 10_000_000:
                    continue
            elif key == "sequence":
                if type(value) is not int or not 0 <= value <= 2**53:
                    continue
            elif key == "sample_rate":
                if value not in {8000, 16000}:
                    continue
            elif key == "source":
                if value not in {"urc", "poll", "cleanup", "runner"}:
                    continue
            elif key == "event_source":
                if value not in {"pipeline", "error_observer", "setup"}:
                    continue
            elif key in {"processor_usable", "release_confirmed"} and type(value) is not bool:
                continue
            row[key] = value
        with self._lock:
            if self._closed:
                return
            self.sequence += 1
            row["sequence"] = self.sequence
            try:
                self._queue.put_nowait(row)
            except queue.Full:
                self.dropped += 1

    def _write(self):
        try:
            while True:
                row = self._queue.get()
                if row is None:
                    break
                try:
                    self._stream.write(json.dumps(row, separators=(",", ":")) + "\n")
                    self._stream.flush()
                    if self._on_record:
                        self._on_record(row)
                except Exception:
                    self.dropped += 1
        finally:
            self._stream.close()

    def close(self):
        # Caller closes this in a background thread after pipeline cleanup.
        with self._lock:
            if self._closed:
                return
            self._closed = True
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            self._queue.get_nowait()
            self.dropped += 1
            self._queue.put_nowait(None)
        self._writer.join(timeout=5)
