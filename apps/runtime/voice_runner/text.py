"""Text transport state and Pipecat adapters. No speech/audio components."""

from __future__ import annotations

import asyncio
import json
from collections import deque
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from pipecat.frames.frames import (
    BotStoppedSpeakingFrame,
    DataFrame,
    EndFrame,
    ErrorFrame,
    InterruptionFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMMessagesAppendFrame,
    TextFrame,
    TTSSpeakFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from voice_runtime.execution.redaction import redact


@dataclass
class TextCompletionFrame(DataFrame):
    generation_id: str = ""


class TextState:
    def __init__(self, session):
        self.session = session
        self.sequence = 0
        self.records = []
        self.checkpoint = session.request.checkpoint
        self.checkpoint_dirty = True
        self.replay = deque(maxlen=4000)
        self.queue = None
        self.ready = asyncio.Event()
        self.active = None
        self.ended = False
        self.paused = False
        self.disconnect_task = None
        self.lock = asyncio.Lock()
        self.commands = set()
        self.uncertain = False
        self.pending_tasks = set()
        self.failed_generations = set()
        self.failure_reported = False

    def clean(self, data):
        return redact(data, self.session.tracker._secrets)

    def emit(self, event):
        self.sequence += 1
        event = self.clean(
            {
                "conversation_id": str(self.session.request.conversation_id),
                "run_id": self.session.run_id,
                "sequence": self.sequence,
                "timestamp": datetime.now(UTC).isoformat(),
                **event,
            }
        )
        self.replay.append(event)
        if self.queue is not None:
            try:
                self.queue.put_nowait(event)
            except asyncio.QueueFull:
                # A slow browser must not block pipeline processing; reconnect replays events.
                self.queue = None
        return event

    async def record(self, kind, payload, *, message_id=None):
        async with self.lock:
            event = self.emit(
                {
                    "type": "message",
                    "id": message_id or str(uuid4()),
                    "kind": kind,
                    "payload": payload,
                }
            )
            self.records.append(
                {
                    "id": event["id"],
                    "sequence": event["sequence"],
                    "kind": kind,
                    "payload": event["payload"],
                }
            )
            if len(self.records) > 2000:
                raise BufferError("Text evidence backlog exhausted")
            await self.session.persist_aux()
            if (
                kind in {"error", "state"}
                or len(self.records) >= 100
                or sum(len(json.dumps(r)) for r in self.records) >= 256 * 1024
            ):
                self.session.wake.set()
        return event

    def schedule(self, coroutine):
        task = asyncio.create_task(coroutine)
        self.pending_tasks.add(task)
        task.add_done_callback(self.pending_tasks.discard)
        task.add_done_callback(self.task_error)

    def task_error(self, task):
        if not task.cancelled() and task.exception():
            self.emit(
                {
                    "type": "error",
                    "stage": "persistence",
                    "message": "Chat evidence could not be saved; execution is stopping.",
                    "diagnostic_id": str(uuid4()),
                }
            )
            self.session.manager.capacity.storage_healthy = False
            if self.session.task:
                self.session.task.cancel()

    def evidence(self, record):
        # Only finalized operation records, never tokens. Exact inputs stay in inspector.
        if record["kind"] in {
            "operation_started",
            "span",
            "tool_started",
            "tool_result",
            "tool_ended",
            "flow_visit_started",
            "interruption",
            "diagnostic",
            "tool_result_context_updated",
            "tool_result_consumed",
            "flow_visit_ended",
            "classifier_result",
            "classifier_context_updated",
            "classifier_result_consumed",
        }:
            self.schedule(self.record("evidence", record))
        if record["kind"] == "tool_started":
            self.checkpoint = {**(self.checkpoint or {}), "safe": False}
            self.checkpoint_dirty = True
        payload = record.get("payload") or record.get("output_payload") or {}
        if (
            record["kind"] in {"tool_result", "tool_ended"}
            and isinstance(payload, dict)
            and payload.get("status") == "uncertain"
        ):
            self.uncertain = True
            self.checkpoint = {**(self.checkpoint or {}), "safe": False}
            self.checkpoint_dirty = True
        if record["kind"] == "diagnostic" and record.get("severity") == "error":
            self.schedule(
                self.failure(
                    "provider" if "provider" in record.get("category", "") else "runtime",
                    record.get("message", "Execution failed"),
                    record.get("diagnostic_id"),
                )
            )

    async def failure(self, stage, message, diagnostic_id=None):
        # Preserve pipeline evidence, but do not replace the actionable provider
        # error with generic shutdown consequences in the chat.
        if stage == "runtime" and self.failure_reported:
            return
        self.failure_reported = True
        payload = {
            "stage": stage,
            "message": message,
            "diagnostic_id": diagnostic_id or str(uuid4()),
            "timestamp": datetime.now(UTC).isoformat(),
        }
        if self.active:
            self.failed_generations.add(self.active["generation_id"])
            await self.complete("failed")
        await self.record("error", payload)
        self.emit({"type": "error", **payload})

    def start(self):
        generation = str(uuid4())
        operation = self.session.host.observer.llm_operation if self.session.host else None
        self.active = {
            "text": "",
            "status": "streaming",
            "generation_id": generation,
            "id": str(uuid4()),
            "operation_id": operation["operation_id"] if operation else None,
            "exchange_id": self.session.tracker.current,
        }
        self.emit({"type": "generation_start", **self.active})

    def delta(self, text):
        if self.active:
            self.active["text"] += text
            self.emit(
                {
                    "type": "delta",
                    "generation_id": self.active["generation_id"],
                    "id": self.active["id"],
                    "text": self.clean(text),
                }
            )

    async def complete(self, status):
        active, self.active = self.active, None
        if active:
            if active["text"] or status != "completed":
                await self.record(
                    "assistant", {**active, "status": status}, message_id=active["id"]
                )
            self.emit(
                {
                    "type": "generation_end",
                    "generation_id": active["generation_id"],
                    "status": status,
                }
            )

    async def checkpoint_now(self):
        host = self.session.host
        if not host or not host.flow:
            return
        context = deepcopy(host.context.get_messages())
        # Do not resume a context containing incomplete tool call/result pairs.
        requested = {t["id"] for m in context for t in m.get("tool_calls", [])}
        answered = {m.get("tool_call_id") for m in context if m.get("role") == "tool"}
        safe = not self.uncertain and not host.tracker._active_tools and requested <= answered
        self.checkpoint_dirty = True
        self.checkpoint = self.clean(
            {
                "safe": safe,
                "messages": context,
                "dialogue": deepcopy(host.tracker.dialogue),
                "node": host.flow.current_node,
                "state": deepcopy(host.flow.state),
                "exchange_count": host._exchange_count,
                "pending_context": deepcopy(host.pending_context),
                "command_ids": list(self.commands),
            }
        )
        await self.session.persist_aux()
        self.session.wake.set()

    async def interrupt(self):
        host = self.session.host
        generating = self.active is not None or bool(host and host.tracker._active_tools)
        if generating and host and host.worker:
            await host.worker.queue_frame(InterruptionFrame())
            await self.complete("interrupted")

    async def command(self, body):
        command = body.get("type")
        command_id = body.get("id")
        if not isinstance(command_id, str) or len(command_id) > 100:
            raise ValueError("A stable command ID is required")
        if command_id in self.commands:
            self.emit({"type": "command_ack", "id": command_id})
            return
        if command not in {"user_message", "cancel", "end"}:
            raise ValueError("Unsupported chat command")
        if command == "user_message":
            text = body.get("text")
            if not isinstance(text, str) or not text.strip() or len(text) > 8000:
                raise ValueError("Enter a message of 1 to 8000 characters")
        self.commands.add(command_id)
        if command == "end":
            self.ended = True
            await self.interrupt()
            await self.checkpoint_now()
            await self.session.host.worker.queue_frame(EndFrame())
        elif command == "cancel":
            await self.interrupt()
            # Worker processes interruption before a later user message.
        else:
            await self.interrupt()
            host = self.session.host
            host.tracker.user_message(text.strip(), datetime.now(UTC).isoformat())
            await self.record(
                "user", {"text": text.strip(), "status": "completed"}, message_id=command_id
            )
            host._exchange_count += 1
            await host._run_classifier_cadence()
            await host.worker.queue_frame(
                LLMMessagesAppendFrame(
                    messages=[{"role": "user", "content": text.strip()}], run_llm=True
                )
            )
        self.emit({"type": "command_ack", "id": command_id})

    async def disconnected(self):
        self.session.connected = False
        await self.interrupt()
        await asyncio.sleep(30)
        if self.session.connected or self.session.closed.is_set():
            return
        self.paused = True
        await self.checkpoint_now()
        if self.session.task:
            self.session.task.cancel()


class TextOutput(FrameProcessor):
    def __init__(self, state):
        super().__init__()
        self.state = state
        self.host = None

    def commit_processor(self):
        return TextCommit(self.state)

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        if direction == FrameDirection.DOWNSTREAM:
            if isinstance(frame, LLMFullResponseStartFrame):
                self.state.start()
            elif isinstance(frame, TTSSpeakFrame):
                await self.state.record(
                    "assistant",
                    {"text": frame.text, "status": "completed", "configured_action": True},
                )
                if frame.append_to_context:
                    self.host.context.add_message({"role": "assistant", "content": frame.text})
                await self.push_frame(BotStoppedSpeakingFrame())
                return
            elif isinstance(frame, TextFrame):
                self.state.delta(frame.text)
            elif isinstance(frame, LLMFullResponseEndFrame):
                generation = self.state.active["generation_id"] if self.state.active else ""
                await self.push_frame(frame, direction)
                await self.push_frame(TextCompletionFrame(generation_id=generation), direction)
                return
            elif isinstance(frame, ErrorFrame):
                await self.state.failure(
                    "provider",
                    "The provider could not complete this response. Inspect the diagnostic details.",
                )
        await self.push_frame(frame, direction)


class TextCommit(FrameProcessor):
    def __init__(self, state):
        super().__init__()
        self.state = state

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        if direction == FrameDirection.DOWNSTREAM:
            if isinstance(frame, TextCompletionFrame):
                if self.state.active and self.state.active["generation_id"] != frame.generation_id:
                    return
                await self.state.complete("completed")
                await self.state.checkpoint_now()
                await self.push_frame(BotStoppedSpeakingFrame())
            elif isinstance(frame, InterruptionFrame):
                await self.state.complete("interrupted")
                await self.state.checkpoint_now()
        await self.push_frame(frame, direction)


class EvidenceMirror:
    def __init__(self, spool, state):
        self.spool, self.state = spool, state

    def submit(self, record):
        self.spool.submit(record)
        self.state.evidence(record)

    def fail(self, error):
        self.spool.fail(error)


async def run_text(session):
    from voice_shared.logging import run_id

    scope = run_id.set(session.run_id)
    session.task = asyncio.current_task()
    session.state = "running"
    state = session.text
    try:
        host = session.make_host()
        output = TextOutput(state)
        await host.prepare(session.request.snapshot, session.tracker, text_output=output)
        host.tracker.begin("greeting")
        checkpoint = session.request.checkpoint
        if checkpoint:
            state.commands.update(checkpoint.get("command_ids", []))
            host.flow.state.update(checkpoint["state"])
            node = dict(host._node(checkpoint["node"]))
            # Restore bindings without replaying lifecycle actions or triggering a response.
            node.update(
                pre_actions=[], post_actions=[], respond_immediately=False, task_messages=[]
            )
            classifier = host.flow._classifier_runner

            async def no_classifier(*args):
                return None

            host.flow._classifier_runner = no_classifier
            await host.flow.initialize(node)
            host.flow._classifier_runner = classifier
            host.context.set_messages(deepcopy(checkpoint["messages"]))
            host.tracker.dialogue = deepcopy(checkpoint.get("dialogue", []))
            host.pending_context = deepcopy(checkpoint.get("pending_context", {}))
            host._exchange_count = checkpoint.get("exchange_count", 0)
        else:
            background = session.request.snapshot.get("_caller_background")
            if background:
                host.flow.state["test_caller_background"] = background
            node = host._node(session.request.snapshot["flow"]["initial_node"])
            if background:
                node = {
                    **node,
                    "task_messages": [
                        *node.get("task_messages", []),
                        {
                            "role": "system",
                            "content": "Tester supplied caller background (unverified; never evidence of completed actions): "
                            + background,
                        },
                    ],
                }
            await host.flow.initialize(node)
        state.ready.set()
        state.emit({"type": "state", "state": "connected"})
        async with asyncio.timeout(min(session.manager.settings.call_max_duration_seconds, 1800)):
            await host.runner_task
        if host.errors:
            raise RuntimeError("Text pipeline failed")
        session.termination.pipeline_finished()
        state.ended = not state.paused
    except TimeoutError:
        await state.failure(
            "limit",
            "The text session reached its maximum duration. Resume from a safe checkpoint or start a new conversation.",
        )
        session.termination.request("duration_limit")
    except asyncio.CancelledError:
        if not state.ended and not state.paused:
            await state.failure(
                "runtime", "Execution stopped: session lease, shutdown or operator stop."
            )
        session.termination.request("cancelled")
    except Exception:
        import sys

        from pydantic import ValidationError
        from voice_shared.logging import exception_event

        diagnostic = exception_event("voice-runtime", sys.exception())
        configuration_error = (
            isinstance(sys.exception(), ValidationError) and not state.ready.is_set()
        )
        await state.failure(
            "configuration" if configuration_error else "runtime",
            (
                "Saved configuration failed runtime validation. Review flow transitions and tool routing, then start a new conversation."
                if configuration_error
                else "The text pipeline failed. Inspect diagnostics or start a new conversation."
            ),
            diagnostic if isinstance(diagnostic, str) else None,
        )
        session.termination.request("pipeline_failure")
    finally:
        state.ready.set()
        await state.complete("interrupted" if state.paused else "failed")
        if state.pending_tasks:
            await asyncio.gather(*tuple(state.pending_tasks), return_exceptions=True)
        await state.checkpoint_now()
        await asyncio.shield(
            session.finish(
                {"chat_state": "paused" if state.paused else "ended" if state.ended else "failed"}
            )
        )
        state.emit(
            {
                "type": "state",
                "state": "paused" if state.paused else "ended" if state.ended else "failed",
            }
        )
        run_id.reset(scope)
