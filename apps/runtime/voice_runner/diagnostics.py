"""Lower-priority bounded, sanitized diagnostic capture outside the audio loop."""

import json
import queue
import threading
from pathlib import Path

from voice_shared.logging import redact


class DiagnosticCapture:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.queue = queue.Queue(512)
        self.closed = False
        self.dropped = 0
        self.writer = threading.Thread(target=self.write, daemon=True, name="runtime-diagnostics")
        self.writer.start()

    def submit(self, event):
        if self.closed:
            self.dropped += 1
            return
        try:
            self.queue.put_nowait(json.dumps(redact(event), separators=(",", ":")) + "\n")
        except queue.Full:
            self.dropped += 1

    def write(self):
        size = 0
        try:
            f = self.path.open("w", encoding="utf-8")
        except OSError:
            f = None
        try:
            while True:
                item = self.queue.get()
                try:
                    if item is None:
                        return
                    size += len(item.encode())
                    if f and size <= 20_000_000:
                        f.write(item)
                    else:
                        self.dropped += 1
                except OSError:
                    self.dropped += 1
                finally:
                    self.queue.task_done()
        finally:
            if f:
                f.close()

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.queue.put(None, timeout=1)
        self.writer.join(5)
        if self.writer.is_alive():
            raise TimeoutError("Diagnostic writer did not close")
