"""Finalize provider and speech operations from Pipecat's actual frame flow."""

from __future__ import annotations

import copy
import json
import time
from collections import deque
from pathlib import Path

from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    ErrorFrame,
    FunctionCallsStartedFrame,
    InterruptionFrame,
    LLMContextFrame,
    LLMFullResponseEndFrame,
    MetricsFrame,
    TextFrame,
    TranscriptionFrame,
    TTSStoppedFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.metrics.metrics import (
    LLMUsageMetricsData,
    ProcessingMetricsData,
    STTUsageMetricsData,
    TextAggregationMetricsData,
    TTFAMetricsData,
    TTFATMetricsData,
    TTFBMetricsData,
    TTSUsageMetricsData,
)
from pipecat.observers.base_observer import BaseObserver, FrameProcessed, FramePushed
from pipecat.processors.frame_processor import FrameDirection
from voice_shared.dev_visibility import is_development

from voice_runtime.diagnostics import (
    provider_error_diagnostic,
    provider_exception_diagnostic,
)
from voice_runtime.execution.exchange import ExchangeTracker
from voice_runtime.safe_logs import opaque_id, safe_event_payload


class EvidenceObserver(BaseObserver):
    """No per-token or PCM records. One span per request, utterance, or playback."""

    def __init__(
        self,
        tracker: ExchangeTracker,
        *,
        llm,
        stt,
        tts,
        llm_provider: str = "groq",
        stt_provider: str = "sarvam",
        tts_provider: str = "sarvam",
        llm_model: str,
        stt_model: str,
        tts_model: str,
        log_path: Path | None = None,
    ) -> None:
        super().__init__()
        self.tracker = tracker
        self.llm, self.stt, self.tts = llm, stt, tts
        self.providers = {"llm": llm_provider, "stt": stt_provider, "tts": tts_provider}
        self.models = {"llm": llm_model, "stt": stt_model, "tts": tts_model}
        self.llm_operation: dict | None = None
        self.stt_operation: dict | None = None
        self.speech_operation: dict | None = None
        self.tts_operation: dict | None = None
        self.playback_operation: dict | None = None
        self.llm_text: list[str] = []
        self.tts_text: list[str] = []
        self.metrics: dict[str, dict] = {"llm": {}, "stt": {}, "tts": {}}
        self.function_operations: dict[str, str] = {}
        self.function_calls: list[dict] = []
        self.last_speech_operation_id: str | None = None
        self.last_tts_operation_id: str | None = None
        self._seen_error_frames = deque(maxlen=256)
        self._seen_interruption_frames: set[int] = set()
        self._vad_stop_clock_ns: int | None = None
        self.context_event_consumer = None
        self.context_summary_idle = None
        self._log = log_path.open("a", encoding="utf-8") if log_path else None

    def _mark(self, event: str, **details) -> None:
        if self._log is not None:
            self._log.write(
                json.dumps(
                    safe_event_payload(event, run_id=opaque_id(self.tracker.run_id), **details)
                )
                + "\n"
            )
            self._log.flush()

    async def on_process_frame(self, data: FrameProcessed) -> None:
        if data.processor is self.llm and isinstance(data.frame, LLMContextFrame):
            if self.llm_operation is not None:
                self._finish_llm("cancelled")
            context = data.frame.context
            tools = context.tools
            payload = {
                "messages": copy.deepcopy(context.get_messages()),
                "tools": [tool.to_default_dict() for tool in tools.standard_tools]
                if hasattr(tools, "standard_tools")
                else [],
                "system_instruction": getattr(
                    getattr(self.llm, "_settings", None), "system_instruction", None
                ),
            }
            exchange_id = self.tracker.current
            self.llm_operation = self.tracker.start_operation(
                "inference",
                "llm",
                provider=getattr(self.llm, "active_provider", self.providers["llm"]),
                model=getattr(self.llm, "active_model", self.models["llm"]),
                input_payload=payload,
                parent_operation_id=self.last_speech_operation_id,
            )
            self.tracker.consume_results(exchange_id, self.llm_operation["operation_id"])
            self.tracker.consume_classifier_results(
                context.get_messages(), exchange_id, self.llm_operation["operation_id"]
            )
            if self.context_event_consumer is not None:
                await self.context_event_consumer(
                    context.get_messages(), exchange_id, self.llm_operation["operation_id"]
                )
            self.llm_text, self.function_calls, self.metrics["llm"] = [], [], {}
            self._mark("llm_started")
        elif data.processor is self.tts and isinstance(data.frame, TextFrame):
            if self.tts_operation is None:
                self.tts_operation = self.tracker.start_operation(
                    "synthesis",
                    "tts",
                    provider=self.providers["tts"],
                    model=self.models["tts"],
                    input_payload={"text": data.frame.text},
                    parent_operation_id=(
                        self.llm_operation["operation_id"] if self.llm_operation else None
                    ),
                )
                self.last_tts_operation_id = self.tts_operation["operation_id"]
                self.tts_text, self.metrics["tts"] = [], {}
                self._mark("tts_started")
            self.tts_text.append(data.frame.text)

    async def on_push_frame(self, data: FramePushed) -> None:
        frame = data.frame
        source = data.source
        if isinstance(frame, VADUserStartedSpeakingFrame):
            self._vad_stop_clock_ns = None
            self._mark("vad_speech_started", processor=type(source).__name__)
        elif isinstance(frame, VADUserStoppedSpeakingFrame):
            self._vad_stop_clock_ns = time.monotonic_ns()
            self._mark("vad_speech_stopped", processor=type(source).__name__)
        if isinstance(frame, MetricsFrame):
            self._metrics(source, frame)
        if isinstance(frame, ErrorFrame):
            # The same error passes through several processors. Persist it once.
            if frame.id in self._seen_error_frames:
                return
            self._seen_error_frames.append(frame.id)
            processor = getattr(frame, "processor", None) or source
            operation_name = (
                "llm"
                if processor is self.llm
                else "stt"
                if processor is self.stt
                else "tts"
                if processor is self.tts
                else "runtime"
            )
            exception = getattr(frame, "exception", None)
            provider = self.providers.get(operation_name, "pipecat")
            if exception is not None:
                diagnostic = provider_exception_diagnostic(
                    exception, provider=provider, operation=operation_name
                )
            else:
                diagnostic = provider_error_diagnostic(
                    provider=provider,
                    body=frame.error,
                    request_id=getattr(processor, "_request_id", None),
                )
                diagnostic["metadata"]["operation"] = operation_name
            diagnostic["metadata"]["pipecat_error_category"] = (
                frame.category.value if frame.category is not None else "unknown"
            )
            if processor is not None and hasattr(processor, "is_usable"):
                diagnostic["metadata"]["processor_is_usable"] = bool(processor.is_usable)
            active = (
                getattr(self, f"{operation_name}_operation", None)
                if operation_name in self.providers
                else None
            )
            if active is not None:
                diagnostic.setdefault("metadata", {})["operation_id"] = active["operation_id"]
            self.tracker.diagnostic(**diagnostic)
            if active is not None:
                self.tracker.finish_operation(
                    active,
                    "failed",
                    output_payload={
                        "error": diagnostic if is_development() else diagnostic["message"]
                    },
                    output_state="failed",
                    **self.metrics[operation_name],
                )
                setattr(self, f"{operation_name}_operation", None)
            self._mark(
                "provider_error",
                provider=provider,
                operation=operation_name,
                code=diagnostic.get("code"),
                http_status=diagnostic.get("http_status"),
                provider_request_id=diagnostic.get("provider_request_id"),
                failed_generation=diagnostic.get("metadata", {}).get("failed_generation"),
                **({"diagnostic": diagnostic} if is_development() else {}),
            )
            if operation_name == "llm" and self.context_summary_idle is not None:
                await self.context_summary_idle()
        if source is self.llm:
            if (
                data.direction == FrameDirection.DOWNSTREAM
                and isinstance(frame, TextFrame)
                and not isinstance(frame, TranscriptionFrame)
            ):
                self.llm_text.append(frame.text)
            elif isinstance(frame, FunctionCallsStartedFrame):
                for call in frame.function_calls:
                    if self.llm_operation:
                        self.function_operations[call.tool_call_id] = self.llm_operation[
                            "operation_id"
                        ]
                    self.function_calls.append(
                        {
                            "id": call.tool_call_id,
                            "name": call.function_name,
                            "arguments": dict(call.arguments),
                        }
                    )
            elif isinstance(frame, LLMFullResponseEndFrame):
                self._finish_llm("completed")
                if self.context_summary_idle is not None:
                    await self.context_summary_idle()
        if source is self.stt and isinstance(frame, TranscriptionFrame) and frame.finalized:
            if self.stt_operation is not None:
                if self._vad_stop_clock_ns is not None:
                    self.metrics["stt"]["ttfs_ms"] = (
                        time.monotonic_ns() - self._vad_stop_clock_ns
                    ) / 1_000_000
                    self._vad_stop_clock_ns = None
                self.tracker.finish_operation(
                    self.stt_operation,
                    "completed",
                    output_payload={
                        "text": frame.text,
                        "language": str(frame.language) if frame.language else None,
                    },
                    output_state="recorded" if frame.text else "empty",
                    **self.metrics["stt"],
                )
                self.stt_operation = None
                self._mark("stt_final")
        if source is self.tts and isinstance(frame, TTSStoppedFrame):
            if self.tts_operation is not None:
                self.tracker.finish_operation(
                    self.tts_operation,
                    "completed",
                    output_payload={"text": "".join(self.tts_text)},
                    output_state="recorded" if "".join(self.tts_text) else "empty",
                    **self.metrics["tts"],
                )
                self.tts_operation = None
                self._mark("tts_stopped")
        if isinstance(frame, InterruptionFrame):
            frame_id = id(frame)
            if frame_id not in self._seen_interruption_frames:
                self._seen_interruption_frames.add(frame_id)
                self.tracker.interrupt(
                    source="caller",
                    reason="caller_barge_in",
                    frame_type=type(frame).__name__,
                )
                self.llm_operation = None
                self.tts_operation = None
                self.playback_operation = None
        if isinstance(frame, UserStartedSpeakingFrame) and self.speech_operation is None:
            self._finish_missing_stt()
            self.speech_operation = self.tracker.start_operation("caller speech", "speech")
            self.last_speech_operation_id = self.speech_operation["operation_id"]
            self.stt_operation = self.tracker.start_operation(
                "transcription",
                "stt",
                provider=self.providers["stt"],
                model=self.models["stt"],
                parent_operation_id=self.speech_operation["operation_id"],
            )
            self.metrics["stt"] = {}
            self._mark("caller_started")
        elif isinstance(frame, UserStoppedSpeakingFrame) and self.speech_operation is not None:
            self.tracker.finish_operation(
                self.speech_operation, "completed", output_state="not_applicable"
            )
            self.speech_operation = None
            self._mark("caller_stopped")
        if isinstance(frame, BotStartedSpeakingFrame) and self.playback_operation is None:
            self.playback_operation = self.tracker.start_operation(
                "serial playback",
                "playback",
                parent_operation_id=self.last_tts_operation_id,
            )
            self._mark("playback_started")
        elif isinstance(frame, BotStoppedSpeakingFrame) and self.playback_operation is not None:
            self.tracker.finish_operation(
                self.playback_operation, "completed", output_state="not_applicable"
            )
            self.playback_operation = None
            self._mark("playback_stopped")
        if isinstance(frame, InterruptionFrame):
            self._mark("interrupted", reason="caller_barge_in")

    def record_turn_event(self, event: str, *, strategy: str | None = None) -> None:
        """Record Pipecat's selected turn strategy without copying caller content."""
        timeout = event == "user_turn_stop_timeout"
        self.tracker.diagnostic(
            severity="warning" if timeout else "info",
            category="turn_decision",
            source="runtime",
            code=event,
            message=(
                "Pipecat ended the caller turn using its fallback timeout"
                if timeout
                else f"Pipecat {event.replace('_', ' ')}"
            ),
            metadata={"strategy": strategy} if strategy else {},
        )
        self._mark(event, strategy=strategy)

    def _finish_missing_stt(self) -> None:
        if self.stt_operation is None:
            return
        self.tracker.finish_operation(
            self.stt_operation,
            "failed",
            output_state="failed",
            failure_reason="missing_final_transcription",
        )
        self.tracker.diagnostic(
            severity="warning",
            category="stt_incomplete_turn",
            source="runtime",
            code="final_transcription_missing",
            message="No finalized transcription was received for a caller turn",
            detail="The STT operation remained open when another turn started or the pipeline ended.",
        )
        self.stt_operation = None
        self._mark("stt_missing_final")

    def _metrics(self, source, frame: MetricsFrame) -> None:
        category = (
            "llm"
            if source is self.llm
            else "tts"
            if source is self.tts
            else "stt"
            if source is self.stt
            else None
        )
        for metric in frame.data:
            metric_category = (
                "stt"
                if isinstance(metric, STTUsageMetricsData)
                else "tts"
                if isinstance(metric, (TTSUsageMetricsData, TextAggregationMetricsData))
                else category
            )
            if metric_category is None:
                continue
            values = self.metrics[metric_category]
            if isinstance(metric, TTFBMetricsData):
                values["ttfb_ms"] = metric.value * 1000
            elif isinstance(metric, TTFAMetricsData):
                values["ttfa_ms"] = metric.ttfa * 1000
            elif isinstance(metric, TTFATMetricsData):
                values["ttfat_ms"] = metric.ttfat * 1000
            elif isinstance(metric, LLMUsageMetricsData):
                values["prompt_tokens"] = metric.value.prompt_tokens
                values["completion_tokens"] = metric.value.completion_tokens
                values["total_tokens"] = metric.value.total_tokens
                values["cache_read_input_tokens"] = metric.value.cache_read_input_tokens
                values["cache_creation_input_tokens"] = metric.value.cache_creation_input_tokens
                values["reasoning_tokens"] = metric.value.reasoning_tokens
            elif isinstance(metric, ProcessingMetricsData):
                values["processing_ms"] = metric.value * 1000
            elif isinstance(metric, STTUsageMetricsData):
                values["audio_seconds"] = metric.value.audio_seconds
            elif isinstance(metric, TTSUsageMetricsData):
                values["tts_characters"] = metric.value
            elif isinstance(metric, TextAggregationMetricsData):
                values["text_aggregation_ms"] = metric.value * 1000

    def _finish_llm(self, status: str) -> None:
        if self.llm_operation is None:
            return
        metrics = self.metrics["llm"]
        effective_provider = getattr(self.llm, "active_provider", self.providers["llm"])
        effective_model = getattr(self.llm, "active_model", self.models["llm"])
        fallback_used = bool(getattr(self.llm, "_fallback_active", False))
        self.llm_operation["provider"] = effective_provider
        self.llm_operation["model"] = effective_model
        self.tracker.finish_operation(
            self.llm_operation,
            status,
            output_payload={
                "text": "".join(self.llm_text),
                "tool_calls": self.function_calls,
                "provider": effective_provider,
                "model": effective_model,
            },
            primary_provider=self.providers["llm"] if fallback_used else None,
            primary_model=self.models["llm"] if fallback_used else None,
            fallback_used=fallback_used,
            output_state=(
                "interrupted"
                if status in {"cancelled", "interrupted"}
                else "recorded"
                if self.llm_text
                else "empty"
            ),
            **metrics,
        )
        self.llm_operation = None
        self._mark("llm_ended", status=status)

    def close(self) -> None:
        self._finish_llm("cancelled")
        self._finish_missing_stt()
        for name in ("stt_operation", "speech_operation", "tts_operation", "playback_operation"):
            operation = getattr(self, name)
            if operation is not None:
                self.tracker.finish_operation(operation, "cancelled")
                setattr(self, name, None)
        if self._log is not None:
            self._log.close()
            self._log = None
