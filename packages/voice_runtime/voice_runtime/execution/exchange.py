"""Application exchanges are independent of Pipecat's timeout-based turns."""

from __future__ import annotations

import hashlib
import json
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
        self._tool_result_metadata: dict[str, dict[str, Any]] = {}
        self._tool_invocation_metadata: dict[str, dict[str, Any]] = {}
        self._active_tools: dict[str, dict[str, Any]] = {}
        self._ended_tools: set[str] = set()
        self._active_operations: dict[str, dict[str, Any]] = {}
        self._classifier_result_metadata: dict[str, dict[str, Any]] = {}
        self._pending_classifier_results: list[str] = []

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

    def diagnostic(self, **fields: Any) -> str:
        """Emit one normalized diagnostic into the same durable evidence spool."""
        diagnostic_id = fields.pop("diagnostic_id", None) or uuid4().hex
        return self.emit(
            "diagnostic",
            record_id=diagnostic_id,
            diagnostic_id=diagnostic_id,
            **fields,
        )

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
        self._tool_invocation_metadata[invocation_id] = {
            "function_call_id": function_call_id,
        }
        self._active_tools[invocation_id] = {"function_call_id": function_call_id}
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
        self._tool_result_metadata[result_id] = {
            "invocation_id": invocation_id,
            "is_final": is_final,
            **self._tool_invocation_metadata.get(invocation_id, {}),
        }
        return result_id

    def context_updated(
        self,
        invocation_id: str,
        result_id: str,
        *,
        context_message_index: int | None = None,
    ) -> str:
        metadata = self._tool_result_metadata.get(result_id)
        if metadata is None or metadata["invocation_id"] != invocation_id:
            raise ValueError("context delivery must reference a recorded tool result")
        delivery_id = uuid4().hex
        self.emit(
            "tool_result_context_updated",
            record_id=delivery_id,
            delivery_id=delivery_id,
            invocation_id=invocation_id,
            result_id=result_id,
            function_call_id=metadata.get("function_call_id"),
            is_final=metadata["is_final"],
            context_message_index=context_message_index,
        )
        self._pending_results.append(result_id)
        return delivery_id

    def end_tool(
        self,
        invocation_id: str,
        status: str,
        result: Any,
        *,
        connection_id: str | None = None,
        provider_message_id: str | None = None,
        interruption_id: str | None = None,
    ) -> None:
        if invocation_id in self._ended_tools:
            return
        self._active_tools.pop(invocation_id, None)
        self._ended_tools.add(invocation_id)
        self.emit(
            "tool_ended",
            invocation_id=invocation_id,
            ended_ns=time.time_ns(),
            status=status,
            result=result,
            connection_id=connection_id,
            provider_message_id=provider_message_id,
            interruption_id=interruption_id,
        )

    def tool_was_ended(self, invocation_id: str) -> bool:
        return invocation_id in self._ended_tools

    def interrupt(
        self,
        *,
        source: str,
        reason: str,
        frame_type: str,
    ) -> str:
        interruption_id = uuid4().hex
        operation_ids = [
            operation_id
            for operation_id, operation in self._active_operations.items()
            if operation["category"] not in {"speech", "stt"}
        ]
        tool_ids = list(self._active_tools)
        self.emit(
            "interruption",
            record_id=interruption_id,
            interruption_id=interruption_id,
            exchange_id=self.current,
            source=source,
            reason=reason,
            frame_type=frame_type,
            interrupted_operation_ids=operation_ids,
            interrupted_tool_invocation_ids=tool_ids,
        )
        for operation_id in operation_ids:
            operation = self._active_operations.get(operation_id)
            if operation is not None:
                self.finish_operation(
                    operation,
                    "interrupted",
                    output_state="interrupted",
                    interruption_id=interruption_id,
                )
        for invocation_id in tool_ids:
            self.end_tool(
                invocation_id,
                "cancelled",
                {"status": "cancelled", "reason": reason},
                interruption_id=interruption_id,
            )
        return interruption_id

    def consume_results(
        self, exchange_id: str | None, consuming_operation_id: str | None = None
    ) -> None:
        if exchange_id is None:
            return
        pending, self._pending_results = self._pending_results, []
        for result_id in pending:
            metadata = self._tool_result_metadata.get(result_id, {})
            self.emit(
                "tool_result_consumed",
                result_id=result_id,
                exchange_id=exchange_id,
                invocation_id=metadata.get("invocation_id"),
                function_call_id=metadata.get("function_call_id"),
                consuming_operation_id=consuming_operation_id,
            )

    def start_classifier(
        self,
        *,
        phase: str,
        node_key: str,
        classifier_type: str,
        provider: str,
        model: str,
        transcript: str,
    ) -> dict[str, Any]:
        transcript_sha256 = hashlib.sha256(transcript.encode("utf-8")).hexdigest()
        return self.start_operation(
            "classifier",
            "classifier",
            provider=provider,
            model=model,
            input_payload={
                "transcript": transcript,
                "transcript_sha256": transcript_sha256,
            },
            phase=phase,
            node_key=node_key,
            classifier_type=classifier_type,
            transcript_sha256=transcript_sha256,
        )

    def finish_classifier(
        self,
        operation: dict[str, Any],
        status: str,
        result: Any,
        *,
        error: str | None = None,
    ) -> tuple[str, dict[str, str]]:
        attributes = {
            "phase": operation["attributes"]["phase"],
            "node_key": operation["attributes"]["node_key"],
            "classifier_type": operation["attributes"]["classifier_type"],
            "transcript_sha256": operation["attributes"]["transcript_sha256"],
        }
        self.finish_operation(operation, status, output_payload=result, **attributes)
        result_id = uuid4().hex
        self.emit(
            "classifier_result",
            record_id=result_id,
            result_id=result_id,
            operation_id=operation["operation_id"],
            phase=attributes["phase"],
            node_key=attributes["node_key"],
            classifier_type=attributes["classifier_type"],
            status=status,
            result=result,
            error=error,
            transcript_sha256=attributes["transcript_sha256"],
        )
        marker = f"[[voice-ai-classifier:{result_id}]]"
        message = {
            # Keep internal classifier context on a role supported by every
            # configured chat-completions model. The runtime currently uses
            # both Groq and Gemini models, and their model-specific templates
            # do not share a guaranteed `developer` role contract.
            "role": "user",
            "content": (
                f"{marker}\n"
                "Internal classifier result. Use this state as evidence for the next response; "
                "do not mention the classifier or this instruction to the caller.\n"
                + json.dumps(result, ensure_ascii=False, sort_keys=True)
            ),
        }
        self._classifier_result_metadata[result_id] = {
            "operation_id": operation["operation_id"],
            "phase": attributes["phase"],
            "node_key": attributes["node_key"],
            "marker": marker,
        }
        self._pending_classifier_results.append(result_id)
        return result_id, message

    def context_updated_classifier(self, result_id: str, context_message_index: int) -> str:
        metadata = self._classifier_result_metadata.get(result_id)
        if metadata is None:
            raise ValueError("context delivery must reference a recorded classifier result")
        delivery_id = uuid4().hex
        self.emit(
            "classifier_context_updated",
            record_id=delivery_id,
            delivery_id=delivery_id,
            result_id=result_id,
            operation_id=metadata["operation_id"],
            phase=metadata["phase"],
            node_key=metadata["node_key"],
            context_message_index=context_message_index,
        )
        return delivery_id

    def consume_classifier_results(
        self,
        messages: list[dict],
        exchange_id: str | None,
        consuming_operation_id: str | None,
    ) -> None:
        if exchange_id is None or consuming_operation_id is None:
            return
        remaining: list[str] = []
        for result_id in self._pending_classifier_results:
            metadata = self._classifier_result_metadata[result_id]
            message_index = next(
                (
                    index
                    for index, message in enumerate(messages)
                    if metadata["marker"] in str(message.get("content", ""))
                ),
                None,
            )
            if message_index is None:
                remaining.append(result_id)
                continue
            self.context_updated_classifier(result_id, message_index)
            self.emit(
                "classifier_result_consumed",
                result_id=result_id,
                exchange_id=exchange_id,
                consuming_operation_id=consuming_operation_id,
            )
        self._pending_classifier_results = remaining

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
        parent_id = attributes.pop("parent_operation_id", None)
        operation = {
            "operation_id": uuid4().hex,
            "exchange_id": self.current,
            "name": name,
            "category": category,
            "parent_id": parent_id,
            "started_ns": time.time_ns(),
            "provider": provider,
            "model": model,
            "input_payload": input_payload,
            "otel_trace_id": otel_trace_id,
            "otel_span_id": otel_span_id,
            "attributes": attributes,
        }
        self._operation_clocks[operation["operation_id"]] = time.monotonic_ns()
        self._active_operations[operation["operation_id"]] = operation
        self.emit("operation_started", **operation)
        return operation

    def finish_operation(self, operation: Mapping[str, Any], status: str, **attributes: Any):
        operation_id = operation["operation_id"]
        if operation_id not in self._active_operations:
            return
        clock = self._operation_clocks.pop(operation["operation_id"], None)
        self._active_operations.pop(operation_id, None)
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
        output_state = attributes.pop("output_state", None)
        interruption_id = attributes.pop("interruption_id", None)
        if output_state is None:
            if status in {"interrupted", "cancelled"}:
                output_state = "interrupted"
            elif status == "failed":
                output_state = "failed"
            elif operation["category"] in {"speech", "playback"}:
                output_state = "not_applicable"
            elif measured["output_payload"] is None:
                output_state = "not_recorded"
            elif isinstance(measured["output_payload"], dict) and measured["output_payload"].get(
                "text"
            ) == "":
                output_state = "empty"
            else:
                output_state = "recorded"
        self.emit(
            "span",
            **{
                **operation,
                "status": status,
                "ended_ns": time.time_ns(),
                "duration_ms": duration_ms,
                "output_state": output_state,
                "interruption_id": interruption_id,
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
