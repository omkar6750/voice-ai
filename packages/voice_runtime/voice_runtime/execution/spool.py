"""Bounded admission, fsynced JSONL and replay with stable record IDs.

Admission is memory-only. A dedicated writer performs disk IO; API delivery runs
in a separate async task. Accepted records become durable at flush(). A process
crash can lose the bounded admission queue, never an acknowledged durable record.
Overflow/disk errors latch unhealthy and must terminate the call, not drop records.
One spool instance owns its file; the worker must use a distinct spool per call.
"""

from __future__ import annotations

import asyncio
import json
import os
import queue
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol


class BatchIngestor(Protocol):
    async def ingest(self, records: list[dict[str, Any]]) -> None:
        """Return only after durable idempotent ingestion of every record ID."""
        ...


class DurableSpool:
    def __init__(
        self,
        path: Path,
        *,
        max_bytes: int = 64 * 1024 * 1024,
        capacity: int = 4096,
        max_record_bytes: int = 256 * 1024,
    ):
        if min(max_bytes, capacity, max_record_bytes) <= 0:
            raise ValueError("spool limits must be positive")
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.cursor_path = path.with_suffix(".ack")
        self.max_bytes = max_bytes
        self.max_record_bytes = max_record_bytes
        self._queue: queue.Queue[bytes | None] = queue.Queue(capacity)
        self._lock = threading.Lock()
        self.error: Exception | None = None
        self.closed = False
        self._thread = threading.Thread(target=self._write, daemon=True, name="call-evidence-spool")
        self._thread.start()

    def check(self):
        if self.error:
            raise RuntimeError("durable evidence spool failed") from self.error

    def submit(self, record: Mapping[str, Any]) -> None:
        self.check()
        if self.closed:
            raise RuntimeError("spool is closed")
        try:
            payload = (
                json.dumps(dict(record), ensure_ascii=False, allow_nan=False) + "\n"
            ).encode()
            if len(payload) > self.max_record_bytes:
                raise BufferError("evidence record exceeds size bound")
            self._queue.put_nowait(payload)
        except Exception as exc:
            self.error = exc
            raise

    def _write(self):
        try:
            # A partial trailing line is never uploaded or silently discarded.
            if self.path.exists() and self.path.stat().st_size:
                with self.path.open("rb") as existing:
                    existing.seek(-1, os.SEEK_END)
                    if existing.read(1) != b"\n":
                        raise ValueError("spool has a partial trailing record; recovery required")
            with self.path.open("ab") as stream:
                while True:
                    payload = self._queue.get()
                    try:
                        if payload is None:
                            return
                        with self._lock:
                            if stream.tell() + len(payload) > self.max_bytes:
                                raise BufferError("durable spool disk quota exhausted")
                            stream.write(payload)
                            stream.flush()
                            os.fsync(stream.fileno())
                    finally:
                        self._queue.task_done()
        except Exception as exc:
            self.error = exc

    async def flush(self):
        while self._queue.unfinished_tasks:
            self.check()
            await asyncio.sleep(0.01)
        self.check()

    def _read_batch(self, limit: int):
        with self._lock:
            offset = int(self.cursor_path.read_text()) if self.cursor_path.exists() else 0
            if not self.path.exists():
                return [], offset
            records = []
            with self.path.open("rb") as stream:
                if offset > self.path.stat().st_size:
                    raise ValueError("spool acknowledgement exceeds file size")
                stream.seek(offset)
                for _ in range(limit):
                    line = stream.readline()
                    if not line:
                        break
                    if not line.endswith(b"\n"):
                        raise ValueError("incomplete spool record")
                    records.append(json.loads(line))
                return records, stream.tell()

    def _ack(self, offset: int):
        temporary = self.cursor_path.with_suffix(".ack.tmp")
        with temporary.open("w") as stream:
            stream.write(str(offset))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.cursor_path)

    async def deliver_once(self, ingestor: BatchIngestor, limit: int = 100) -> int:
        records, offset = await asyncio.to_thread(self._read_batch, limit)
        if not records:
            return 0
        await ingestor.ingest(records)
        await asyncio.to_thread(self._ack, offset)
        return len(records)

    async def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            await self.flush()
        finally:
            if self._thread.is_alive() and not self.error:
                self._queue.put_nowait(None)
            await asyncio.to_thread(self._thread.join, 5)
        self.check()
