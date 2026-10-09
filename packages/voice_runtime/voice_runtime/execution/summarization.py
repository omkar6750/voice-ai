"""Complete-exchange cadence and retention helpers for context summarization."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

SUMMARY_MESSAGE_PREFIX = "Conversation summary:"


def estimate_context_tokens(messages: Sequence[Mapping]) -> int:
    """Use the installed Pipecat estimator for consistent context accounting."""
    from pipecat.processors.aggregators.llm_context import LLMContext
    from pipecat.utils.context.llm_context_summarization import (
        LLMContextSummarizationUtil,
    )

    return LLMContextSummarizationUtil.estimate_context_tokens(LLMContext(messages=list(messages)))


def summary_source_is_current(
    *,
    expected_generation: int,
    current_generation: int,
    expected_prefix: Sequence[Mapping],
    current_messages: Sequence[Mapping],
) -> bool:
    """Check that the summary's source is still the current context prefix."""
    return expected_generation == current_generation and list(
        current_messages[: len(expected_prefix)]
    ) == list(expected_prefix)


def should_summarize(
    *,
    completed_exchanges: int,
    estimated_context_tokens: int,
    every_n_exchanges: int,
    context_window_tokens: int,
) -> str | None:
    """Return the first satisfied trigger reason, or None when below both thresholds."""
    if estimated_context_tokens >= context_window_tokens:
        return "context_token_threshold"
    if completed_exchanges >= every_n_exchanges:
        return "completed_exchange_threshold"
    return None


def messages_to_keep_for_recent_exchanges(
    messages: Sequence[Mapping],
    *,
    exchange_count: int,
    active_task_messages: Sequence[Mapping] = (),
) -> int:
    """Choose a tail boundary that preserves whole caller/assistant exchanges.

    Pipecat's summary utility accepts a message count and separately protects
    unresolved tool-call pairs. This converts the requested exchange retention
    to that API's count while also retaining current active task messages.
    """
    if exchange_count < 1:
        raise ValueError("exchange_count must be positive")
    turns: list[tuple[int, int]] = []
    for index, message in enumerate(messages):
        if message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str) and content.startswith(SUMMARY_MESSAGE_PREFIX):
            continue
        next_user = next(
            (
                candidate
                for candidate in range(index + 1, len(messages))
                if messages[candidate].get("role") == "user"
                and not str(messages[candidate].get("content", "")).startswith(
                    SUMMARY_MESSAGE_PREFIX
                )
            ),
            len(messages),
        )
        has_final_assistant = any(
            messages[candidate].get("role") == "assistant"
            and isinstance(messages[candidate].get("content"), str)
            and bool(messages[candidate].get("content", "").strip())
            for candidate in range(index + 1, next_user)
        )
        if has_final_assistant:
            turns.append((index, next_user - 1))

    keep_from = turns[max(0, len(turns) - exchange_count)][0] if turns else 0

    # Flow task messages may carry the active node's semantic instructions inside
    # context. Retain their latest matching occurrence; role_message itself is a
    # provider system instruction and is outside this message list.
    for task in active_task_messages:
        for index in range(len(messages) - 1, -1, -1):
            if dict(messages[index]) == dict(task):
                keep_from = min(keep_from, index)
                break

    return max(0, len(messages) - keep_from)


class SummaryLLMRecorder:
    """Instrument Pipecat's dedicated summary request without entering the voice path."""

    def __init__(self, llm, coordinator):
        self._llm = llm
        self._coordinator = coordinator

    def __getattr__(self, name):
        return getattr(self._llm, name)

    async def _generate_summary(self, frame):
        return await self._coordinator.generate(self._llm, frame)


class ContextSummaryCoordinator:
    """Schedules background summaries and records their lifecycle in run evidence."""

    def __init__(self, *, tracker, context, config, provider, model, llm, credential_available):
        import copy

        self.tracker = tracker
        self.context = context
        self.config = config
        self.provider = provider
        self.model = model
        self.llm = llm
        self.credential_available = credential_available
        self.copy = copy
        self.pending: dict | None = None
        self.deferred_result = None
        self._request_task = None
        self.last_operation_id: str | None = None
        self.summary_text: str | None = None
        self.consumed = False
        self.summarizer = None
        self.flow = None

    def attach(self, assistant_aggregator):
        self.summarizer = assistant_aggregator._summarizer
        self.summarizer._auto_trigger = False

        async def guarded_result(frame):
            pending = self.pending
            if frame.request_id != self.summarizer._pending_summary_request_id:
                return
            if frame.error:
                await self.summarizer._clear_summarization_state()
                if pending is not None:
                    self._diagnostic("failed", frame.error, pending)
                    self.pending = None
                return
            if pending is None:
                await self.summarizer._clear_summarization_state()
                return
            if not self.summarizer._validate_summary_context(frame.last_summarized_index):
                await self.summarizer._clear_summarization_state()
                self._diagnostic("discarded", "Summary boundary is no longer valid", pending)
                self.pending = None
                return
            await self.summarizer._clear_summarization_state()
            foreground = getattr(getattr(self, "observer", None), "llm_operation", None)
            if not summary_source_is_current(
                expected_generation=pending["generation"],
                current_generation=self._generation(),
                expected_prefix=pending["prefix"],
                current_messages=self.context.get_messages(),
            ):
                self._diagnostic(
                    "discarded",
                    "Summary arrived after its source context or active node changed",
                    pending,
                )
                self.pending = None
                return
            if foreground is not None:
                self.deferred_result = frame
                return
            # Pipecat replaces only messages through last_summarized_index and
            # appends the untouched tail. No await occurs before that mutation.
            await self.summarizer._apply_summary(frame.summary, frame.last_summarized_index)

        self.summarizer._handle_summary_result = guarded_result
        assistant_aggregator.add_event_handler("on_summary_applied", self._on_applied)

    async def apply_deferred_if_idle(self):
        frame = self.deferred_result
        pending = self.pending
        if frame is None or pending is None:
            return
        if getattr(getattr(self, "observer", None), "llm_operation", None) is not None:
            return
        if not self.summarizer._validate_summary_context(
            frame.last_summarized_index
        ) or not summary_source_is_current(
            expected_generation=pending["generation"],
            current_generation=self._generation(),
            expected_prefix=pending["prefix"],
            current_messages=self.context.get_messages(),
        ):
            self._diagnostic(
                "discarded",
                "Deferred summary became stale before a safe application point",
                pending,
            )
            self.deferred_result = None
            self.pending = None
            return
        self.deferred_result = None
        # Apply at the response-end boundary, when no foreground inference is
        # reading the shared context. Pipecat preserves the untouched tail.
        await self.summarizer._apply_summary(frame.summary, frame.last_summarized_index)

    def _generation(self):
        return getattr(self.flow, "context_generation", 0)

    def _diagnostic(self, state, message, details):
        self.tracker.diagnostic(
            severity="info" if state in {"applied", "consumed", "discarded"} else "error",
            category="context_summary",
            source="runtime",
            code=state,
            message=message,
            metadata={
                "summary_operation_id": details.get("operation_id") or self.last_operation_id or "",
                "trigger_reason": details.get("trigger_reason", ""),
                "source_message_ids": details.get("source_message_ids", []),
                "generated_at": details.get("generated_at", ""),
                "exchange_id": self.tracker.current or "",
                **details.get("metadata", {}),
            },
        )

    def request(
        self,
        *,
        reason: str,
        completed_exchanges: int,
        caller_turns: int,
        context_tokens: int,
        context_token_source: str,
    ):
        import asyncio

        from pipecat.utils.context.llm_context_summarization import LLMContextSummarizationUtil

        if self.pending is not None or self.summarizer is None:
            return
        messages = self.context.get_messages()
        minimum = messages_to_keep_for_recent_exchanges(
            messages,
            exchange_count=int(self.config.get("preserve_recent_exchanges", 2)),
            active_task_messages=getattr(self.flow, "_current_node_task_messages", ()),
        )
        summary_config = self.summarizer._auto_config.summary_config
        summary_config.min_messages_after_summary = minimum
        selected = LLMContextSummarizationUtil.get_messages_to_summarize(self.context, minimum)
        if selected.last_summarized_index < 0:
            self._diagnostic(
                "deferred",
                "No complete exchange is available to summarize",
                {
                    "trigger_reason": reason,
                    "metadata": {"estimated_context_tokens": estimate_context_tokens(messages)},
                },
            )
            return
        source_ids = self._source_ids(selected.messages)
        digest_input = repr(selected.messages).encode("utf-8", errors="replace")
        import hashlib

        estimated_prompt_tokens = (
            estimate_context_tokens(selected.messages)
            + len(str(self.config.get("prompt", ""))) // 4
        )
        operation = self.tracker.start_operation(
            "context summary",
            "summarizer",
            provider=self.provider,
            model=self.model,
            input_payload={
                "source_message_ids": source_ids,
                "source_message_count": len(selected.messages),
                "source_context_sha256": hashlib.sha256(digest_input).hexdigest(),
                "trigger_reason": reason,
                "summarization_prompt": self.config.get("prompt"),
                "caller_turns": caller_turns,
                "completed_exchanges": completed_exchanges,
                "context_tokens_at_trigger": context_tokens,
                "context_token_source": context_token_source,
            },
            estimated_input_tokens=estimated_prompt_tokens,
        )
        self.last_operation_id = operation["operation_id"]
        self.summary_text = None
        self.consumed = False
        self.pending = {
            "operation": operation,
            "trigger_reason": reason,
            "source_message_ids": source_ids,
            "estimated_prompt_tokens": estimated_prompt_tokens,
            "prefix": self.copy.deepcopy(messages[: selected.last_summarized_index + 1]),
            "last_index": selected.last_summarized_index,
            "generation": self._generation(),
            "request_id": None,
            "generated_at": "",
        }
        if not self.credential_available:
            error = "Summarizer credential is not configured for the selected provider"
            self.tracker.finish_operation(
                operation,
                "failed",
                output_payload={"error": error},
                error=error,
                trigger_reason=reason,
            )
            self._diagnostic("failed", error, self.pending)
            self.pending = None
            return
        self._request_task = asyncio.create_task(
            self._request(minimum), name="context-summary-request"
        )

    async def _request(self, minimum):
        import asyncio

        try:
            summary_config = self.summarizer._auto_config.summary_config
            request_frame = __import__(
                "pipecat.frames.frames", fromlist=["LLMSummarizeContextFrame"]
            ).LLMSummarizeContextFrame(config=summary_config)
            # The frame path keeps Pipecat's request ID and dedicated-LLM task manager.
            await self.summarizer._handle_manual_summarization_request(request_frame)
            if self.pending is not None:
                self.pending["request_id"] = self.summarizer._pending_summary_request_id
                from datetime import datetime

                self.pending["generated_at"] = datetime.now().astimezone().isoformat()
        except asyncio.CancelledError:
            if self.pending is not None:
                error = "Summarization request was cancelled before it started"
                self.tracker.finish_operation(
                    self.pending["operation"],
                    "cancelled",
                    output_payload={"error": error},
                    error=error,
                    trigger_reason=self.pending["trigger_reason"],
                )
                self._diagnostic("failed", error, self.pending)
                self.pending = None
            raise
        except Exception as exc:
            if self.pending is None:
                return
            operation = self.pending["operation"]
            detail = str(exc)
            self.tracker.finish_operation(
                operation,
                "failed",
                output_payload={"error": detail},
                error=detail,
                trigger_reason=self.pending["trigger_reason"],
            )
            self._diagnostic("failed", "Context summarization request failed", self.pending)
            self.pending = None

    async def generate(self, llm, frame):
        import asyncio
        import time
        from datetime import datetime

        pending = self.pending
        started = time.monotonic()
        try:
            result = await llm._generate_summary(frame)
        except asyncio.CancelledError:
            if pending is not None:
                error = "Summarizer request was cancelled before it completed"
                self.tracker.finish_operation(
                    pending["operation"],
                    "cancelled",
                    output_payload={"error": error},
                    error=error,
                    trigger_reason=pending["trigger_reason"],
                )
                self._diagnostic("failed", error, pending)
                self.pending = None
            raise
        except Exception as exc:
            if pending is not None:
                detail = str(exc)
                self.tracker.finish_operation(
                    pending["operation"],
                    "failed",
                    output_payload={"error": detail},
                    error=detail,
                    generated_at=datetime.now().astimezone().isoformat(),
                    trigger_reason=pending["trigger_reason"],
                )
                self._diagnostic("failed", "Summarizer provider request failed", pending)
                pending["generated_at"] = datetime.now().astimezone().isoformat()
                self.pending = None
            raise
        if pending is not None:
            summary, last_index = result
            generated_at = datetime.now().astimezone().isoformat()
            duration_ms = (time.monotonic() - started) * 1000
            self.tracker.finish_operation(
                pending["operation"],
                "completed",
                output_payload={"summary": summary, "last_summarized_index": last_index},
                prompt_tokens=max(1, pending["estimated_prompt_tokens"]),
                completion_tokens=max(1, len(summary) // 4),
                total_tokens=max(
                    2,
                    pending["estimated_prompt_tokens"] + len(summary) // 4,
                ),
                usage_source="estimated_characters_divided_by_four",
                duration_ms=duration_ms,
                generated_at=generated_at,
                trigger_reason=pending["trigger_reason"],
            )
            pending["generated_at"] = generated_at
            pending["duration_ms"] = duration_ms
            pending["last_index"] = last_index
            self.summary_text = summary
        return result

    async def _on_applied(self, _aggregator, _summarizer, event):
        pending = self.pending
        if pending is None:
            return
        self._diagnostic(
            "applied",
            "Context summary applied to the following LLM context",
            {
                **pending,
                "metadata": {
                    "applied_at": __import__("datetime").datetime.now().astimezone().isoformat(),
                    "original_message_count": event.original_message_count,
                    "new_message_count": event.new_message_count,
                    "summarized_message_count": event.summarized_message_count,
                    "preserved_message_count": event.preserved_message_count,
                    "duration_ms": pending.get("duration_ms", 0),
                },
            },
        )
        self.pending = None

    def _source_ids(self, messages):
        entries = getattr(self.tracker, "dialogue", [])
        remaining = list(entries)
        result = []
        for message in messages:
            role = message.get("role")
            content = message.get("content")
            if not isinstance(content, str):
                continue
            match = next(
                (
                    item
                    for item in remaining
                    if item.get("role") == role and item.get("text") == content
                ),
                None,
            )
            if match:
                remaining.remove(match)
                result.append(match.get("message_id", ""))
        return [item for item in result if item]

    async def context_consumed(self, messages, exchange_id, operation_id):
        if self.consumed or not self.last_operation_id:
            return
        summary = next(
            (
                str(message.get("content", ""))[len(SUMMARY_MESSAGE_PREFIX) :].strip()
                for message in messages
                if str(message.get("content", "")).startswith(SUMMARY_MESSAGE_PREFIX)
            ),
            None,
        )
        if summary is None or summary != (self.summary_text or "").strip():
            return
        self.consumed = True
        self._diagnostic(
            "consumed",
            "Context summary was included in an LLM request",
            {
                "operation_id": self.last_operation_id,
                "metadata": {
                    "consuming_llm_operation_id": operation_id,
                    "exchange_id": exchange_id or "",
                    "consumed_at": __import__("datetime").datetime.now().astimezone().isoformat(),
                },
            },
        )
