"""Application exchanges are independent of Pipecat's timeout-based turns."""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any, Protocol
from uuid import uuid4


class RecordSink(Protocol):
    def submit(self, record: Mapping[str, Any]) -> None:
        """Nonblocking admission; raise on overflow rather than silently lose evidence."""
        ...


class ExchangeTracker:
    def __init__(self, call_id: str, sink: RecordSink):
        self.call_id = call_id
        self.sink = sink
        self.current: str | None = None
        self.assistant_exchange: str | None = None
        self._user_turns: dict[str, str] = {}
        self._finalized: set[tuple[str, str, str]] = set()
        self.sequence = 0

    def emit(self, kind: str, *, exchange_id: str | None = None, **data: Any) -> str:
        record_id = uuid4().hex
        self.sink.submit(
            {
                "id": record_id,
                "call_id": self.call_id,
                "kind": kind,
                "exchange_id": exchange_id,
                "timestamp_ns": time.time_ns(),
                **data,
            }
        )
        return record_id

    def begin(self, origin: str) -> str:
        if origin not in {"greeting", "caller"}:
            raise ValueError("exchange origin must be greeting or caller")
        self.sequence += 1
        self.current = uuid4().hex
        self.emit("exchange", exchange_id=self.current, origin=origin, sequence=self.sequence)
        return self.current

    def user_message(self, content: str, timestamp: str) -> str | None:
        if not content.strip():
            return None
        key = ("user", timestamp, content)
        if key in self._finalized:
            return self._user_turns.get(timestamp)
        # Finalized segments with the same aggregator turn timestamp share one exchange.
        exchange = self._user_turns.get(timestamp)
        if exchange is None:
            exchange = self.begin("caller")
            self._user_turns[timestamp] = exchange
        self._finalized.add(key)
        self.emit(
            "message",
            exchange_id=exchange,
            role="user",
            content=content,
            source_timestamp=timestamp,
            finalized=True,
        )
        return exchange

    def assistant_started(self) -> str:
        self.assistant_exchange = self.current or self.begin("greeting")
        return self.assistant_exchange

    def assistant_message(self, content: str, timestamp: str, interrupted: bool = False):
        exchange = self.assistant_exchange or self.current
        self.assistant_exchange = None
        key = ("assistant", timestamp, content)
        if not content.strip() or key in self._finalized:
            return
        self._finalized.add(key)
        self.emit(
            "message",
            exchange_id=exchange,
            role="assistant",
            content=content,
            source_timestamp=timestamp,
            finalized=True,
            interrupted=interrupted,
        )

    def start_operation(self, name: str, category: str, **attributes: Any) -> dict[str, Any]:
        operation = {
            "operation_id": uuid4().hex,
            "exchange_id": self.current,
            "name": name,
            "category": category,
            "started_ns": time.time_ns(),
            "attributes": attributes,
        }
        self.emit("operation_started", **operation)
        return operation

    def finish_operation(self, operation: Mapping[str, Any], status: str, **attributes: Any):
        self.emit(
            "span",
            **{
                **operation,
                "status": status,
                "ended_ns": time.time_ns(),
                "attributes": {**operation["attributes"], **attributes},
            },
        )


def bind_transcripts(aggregators, tracker: ExchangeTracker) -> None:
    @aggregators.user().event_handler("on_user_turn_message_added")
    async def user_message(_aggregator, message):
        tracker.user_message(message.content, message.timestamp)

    @aggregators.assistant().event_handler("on_assistant_turn_started")
    async def assistant_started(_aggregator):
        tracker.assistant_started()

    @aggregators.assistant().event_handler("on_assistant_turn_stopped")
    async def assistant_message(_aggregator, message):
        tracker.assistant_message(message.content, message.timestamp, message.interrupted)
