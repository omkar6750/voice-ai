"""Finalize provider and speech operations from Pipecat's actual frame flow."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
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
)
from pipecat.metrics.metrics import (
    LLMUsageMetricsData,
    ProcessingMetricsData,
    TTFAMetricsData,
    TTFATMetricsData,
    TTFBMetricsData,
)
from pipecat.observers.base_observer import BaseObserver, FrameProcessed, FramePushed
from pipecat.processors.frame_processor import FrameDirection

from voice_runtime.execution.exchange import ExchangeTracker


class EvidenceObserver(BaseObserver):
    """No per-token or PCM records. One span per request, utterance, or playback."""

    def __init__(
        self,
        tracker: ExchangeTracker,
        *,
        llm,
        stt,
        tts,
        llm_model: str,
        stt_model: str,
        tts_model: str,
        log_path: Path | None = None,
    ) -> None:
        super().__init__()
        self.tracker = tracker
        self.llm, self.stt, self.tts = llm, stt, tts
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
        self._seen_interruption_frames: set[int] = set()
        self._log = log_path.open("a", encoding="utf-8") if log_path else None

    def _mark(self, event: str, **details) -> None:
        if self._log is not None:
            self._log.write(json.dumps({"event": event, **details}, ensure_ascii=False) + "\n")
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
                provider="groq",
                model=self.models["llm"],
                input_payload=payload,
                parent_operation_id=self.last_speech_operation_id,
            )
            self.tracker.consume_results(exchange_id, self.llm_operation["operation_id"])
            self.tracker.consume_classifier_results(
                context.get_messages(), exchange_id, self.llm_operation["operation_id"]
            )
            self.llm_text, self.function_calls, self.metrics["llm"] = [], [], {}
            self._mark("llm_started")
        elif data.processor is self.tts and isinstance(data.frame, TextFrame):
            if self.tts_operation is None:
                self.tts_operation = self.tracker.start_operation(
                    "synthesis",
                    "tts",
                    provider=type(self.tts).__name__,
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
        if isinstance(frame, MetricsFrame):
            self._metrics(source, frame)
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
        if source is self.stt and isinstance(frame, TranscriptionFrame) and frame.finalized:
            if self.stt_operation is not None:
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
            self.speech_operation = self.tracker.start_operation("caller speech", "speech")
            self.last_speech_operation_id = self.speech_operation["operation_id"]
            self.stt_operation = self.tracker.start_operation(
                "transcription",
                "stt",
                provider="sarvam",
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
        if category is None:
            return
        values = self.metrics[category]
        for metric in frame.data:
            if isinstance(metric, TTFBMetricsData):
                values["ttfb_ms"] = metric.value * 1000
            elif isinstance(metric, TTFAMetricsData):
                values["ttfa_ms"] = metric.ttfa * 1000
            elif isinstance(metric, TTFATMetricsData):
                values["ttfat_ms"] = metric.ttfat * 1000
            elif isinstance(metric, LLMUsageMetricsData):
                values["prompt_tokens"] = metric.value.prompt_tokens
                values["completion_tokens"] = metric.value.completion_tokens
                values["reasoning_tokens"] = metric.value.reasoning_tokens
            elif isinstance(metric, ProcessingMetricsData):
                values["processing_ms"] = metric.value * 1000

    def _finish_llm(self, status: str) -> None:
        if self.llm_operation is None:
            return
        metrics = self.metrics["llm"]
        self.tracker.finish_operation(
            self.llm_operation,
            status,
            output_payload={"text": "".join(self.llm_text), "tool_calls": self.function_calls},
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
        for name in ("stt_operation", "speech_operation", "tts_operation", "playback_operation"):
            operation = getattr(self, name)
            if operation is not None:
                self.tracker.finish_operation(operation, "cancelled")
                setattr(self, name, None)
        if self._log is not None:
            self._log.close()
            self._log = None
