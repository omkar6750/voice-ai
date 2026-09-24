"""Application exchanges are independent of Pipecat's timeout-based turns."""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any, Protocol
from uuid import uuid4

from voice_runtime.execution.redaction import redact


class RecordSink(Protocol):
    def submit(self, record: Mapping[str, Any]) -> None:
        """Nonblocking admission; raise on overflow rather than silently lose evidence."""
        ...


class ExchangeTracker:
    def __init__(self, run_id: str, sink: RecordSink, *, secrets: tuple[str, ...] = ()):
        self.run_id = run_id
        self.sink = sink
        self._secrets = secrets
        self.current: str | None = None
        self.assistant_exchange: str | None = None
        self._user_turns: dict[str, str] = {}
        self._finalized: set[tuple[str, str, str]] = set()
        self.sequence = 0
        self._message_sequences: dict[str, int] = {}
        self._operation_clocks: dict[str, int] = {}
        self._closed_exchanges: set[str] = set()
        self._visit: dict[str, Any] | None = None
        self._visit_sequence = 0
        self._tool_result_sequences: dict[str, int] = {}
        self._pending_results: list[str] = []

    def emit(
        self,
        kind: str,
        *,
        exchange_id: str | None = None,
        record_id: str | None = None,
        **data: Any,
    ) -> str:
        record_id = record_id or uuid4().hex
        self.sink.submit(
            redact(
                {
                    "id": record_id,
                    "run_id": self.run_id,
                    "kind": kind,
                    **({"exchange_id": exchange_id} if exchange_id is not None else {}),
                    "timestamp_ns": time.time_ns(),
                    **data,
                },
                self._secrets,
            )
        )
        return record_id

    def begin(self, origin: str) -> str:
        if origin not in {"greeting", "caller", "agent"}:
            raise ValueError("exchange origin must be greeting, caller or agent")
        self.end_exchange("completed")
        self.sequence += 1
        self.current = uuid4().hex
        self._message_sequences[self.current] = 0
        self.emit("exchange", exchange_id=self.current, origin=origin, sequence=self.sequence)
        return self.current

    def end_exchange(self, status: str) -> None:
        if self.current is None or self.current in self._closed_exchanges:
            return
        self.emit("exchange_ended", exchange_id=self.current, status=status)
        self._closed_exchanges.add(self.current)

    def start_visit(self, node_key: str, triggered_by_tool_id: str | None = None) -> str:
        self.end_visit("completed")
        self._visit_sequence += 1
        visit = {
            "visit_id": uuid4().hex,
            "span_id": uuid4().hex,
            "node_key": node_key,
            "started_ns": time.time_ns(),
            "started_clock": time.monotonic_ns(),
        }
        self._visit = visit
        self.emit(
            "flow_visit_started",
            visit_id=visit["visit_id"],
            span_id=visit["span_id"],
            sequence=self._visit_sequence,
            node_key=node_key,
            started_ns=visit["started_ns"],
            triggered_by_tool_id=triggered_by_tool_id,
        )
        return visit["visit_id"]

    def end_visit(self, status: str) -> None:
        visit = self._visit
        if visit is None:
            return
        self._visit = None
        self.emit(
            "flow_visit_ended",
            visit_id=visit["visit_id"],
            ended_ns=time.time_ns(),
            duration_ms=(time.monotonic_ns() - visit["started_clock"]) / 1_000_000,
            status=status,
        )

    def start_tool(
        self,
        binding_key: str,
        tool_version_id: str,
        function_call_id: str,
        arguments: dict,
        llm_operation_id: str | None = None,
    ) -> str:
        invocation_id = uuid4().hex
        self._tool_result_sequences[invocation_id] = 0
        self.emit(
            "tool_started",
            invocation_id=invocation_id,
            exchange_id=self.current,
            binding_key=binding_key,
            tool_version_id=tool_version_id,
            function_call_id=function_call_id,
            llm_operation_id=llm_operation_id,
            arguments=arguments,
            started_ns=time.time_ns(),
        )
        return invocation_id

    def tool_result(self, invocation_id: str, payload: Any, *, is_final: bool) -> str:
        sequence = self._tool_result_sequences[invocation_id] + 1
        self._tool_result_sequences[invocation_id] = sequence
        result_id = uuid4().hex
        self.emit(
            "tool_result",
            record_id=result_id,
            invocation_id=invocation_id,
            sequence=sequence,
            payload=payload,
            is_final=is_final,
        )
        self._pending_results.append(result_id)
        return result_id

    def end_tool(
        self,
        invocation_id: str,
        status: str,
        result: Any,
        *,
        connection_id: str | None = None,
        provider_message_id: str | None = None,
    ) -> None:
        self.emit(
            "tool_ended",
            invocation_id=invocation_id,
            ended_ns=time.time_ns(),
            status=status,
            result=result,
            connection_id=connection_id,
            provider_message_id=provider_message_id,
        )

    def consume_results(self, exchange_id: str | None) -> None:
        if exchange_id is None:
            return
        pending, self._pending_results = self._pending_results, []
        for result_id in pending:
            self.emit("tool_result_consumed", result_id=result_id, exchange_id=exchange_id)

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
        self._message_sequences[exchange] += 1
        self.emit(
            "message",
            exchange_id=exchange,
            role="user",
            sequence=self._message_sequences[exchange],
            content=content,
            source_timestamp=timestamp,
            finalized=True,
        )
        return exchange

    def assistant_started(self) -> str:
        self.assistant_exchange = self.current or self.begin("greeting")
        return self.assistant_exchange

    def assistant_message(self, content: str, timestamp: str, interrupted: bool = False):
        exchange = self.assistant_exchange or self.current or self.begin("greeting")
        self.assistant_exchange = None
        key = ("assistant", timestamp, content)
        if not content.strip() or key in self._finalized:
            return
        self._finalized.add(key)
        self._message_sequences[exchange] += 1
        self.emit(
            "message",
            exchange_id=exchange,
            role="assistant",
            sequence=self._message_sequences[exchange],
            content=content,
            source_timestamp=timestamp,
            finalized=True,
            interrupted=interrupted,
        )

    def start_operation(self, name: str, category: str, **attributes: Any) -> dict[str, Any]:
        provider = attributes.pop("provider", None)
        model = attributes.pop("model", None)
        input_payload = attributes.pop("input_payload", None)
        otel_trace_id = attributes.pop("otel_trace_id", None)
        otel_span_id = attributes.pop("otel_span_id", None)
        operation = {
            "operation_id": uuid4().hex,
            "exchange_id": self.current,
            "name": name,
            "category": category,
            "started_ns": time.time_ns(),
            "provider": provider,
            "model": model,
            "input_payload": input_payload,
            "otel_trace_id": otel_trace_id,
            "otel_span_id": otel_span_id,
            "attributes": attributes,
        }
        self._operation_clocks[operation["operation_id"]] = time.monotonic_ns()
        self.emit("operation_started", **operation)
        return operation

    def finish_operation(self, operation: Mapping[str, Any], status: str, **attributes: Any):
        clock = self._operation_clocks.pop(operation["operation_id"], None)
        duration_ms = None if clock is None else (time.monotonic_ns() - clock) / 1000000
        measured = {
            key: attributes.pop(key, None)
            for key in (
                "output_payload",
                "ttfb_ms",
                "ttfa_ms",
                "ttfat_ms",
                "prompt_tokens",
                "completion_tokens",
                "reasoning_tokens",
                "audio_seconds",
            )
        }
        self.emit(
            "span",
            **{
                **operation,
                "status": status,
                "ended_ns": time.time_ns(),
                "duration_ms": duration_ms,
                "attributes": {**operation["attributes"], **attributes},
                **measured,
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
