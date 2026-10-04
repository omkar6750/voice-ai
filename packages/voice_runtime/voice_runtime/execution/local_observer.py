"""Safe lifecycle sampling for the opt-in local runtime trace."""

from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    CancelFrame,
    EndFrame,
    ErrorFrame,
    InterruptionFrame,
    LLMFullResponseEndFrame,
    StartFrame,
    TTSStartedFrame,
    TTSStoppedFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.observers.base_observer import BaseObserver, FramePushed, ProcessorSetUp
from pipecat.observers.error_observer import ErrorObserver
from pipecat.processors.frame_processor import FrameProcessor

_SELECTED = frozenset(
    {
        StartFrame,
        EndFrame,
        CancelFrame,
        ErrorFrame,
        InterruptionFrame,
        BotStartedSpeakingFrame,
        BotStoppedSpeakingFrame,
        TTSStartedFrame,
        TTSStoppedFrame,
        LLMFullResponseEndFrame,
        UserStartedSpeakingFrame,
        UserStoppedSpeakingFrame,
        VADUserStartedSpeakingFrame,
        VADUserStoppedSpeakingFrame,
    }
)


def _processor_role(processor: FrameProcessor) -> str:
    # Processor names and class names may contain provider or customer data.
    name = type(processor).__name__.casefold()
    return next((role for role in ("llm", "stt", "tts") if role in name), "other")


class LocalLifecycleObserver(BaseObserver):
    def __init__(self, trace) -> None:
        super().__init__()
        self.trace = trace

    async def on_push_frame(self, data: FramePushed) -> None:
        frame = data.frame
        frame_type = type(frame).__name__
        if type(frame) in _SELECTED:
            self.trace.record(
                "pipeline_frame",
                component="pipecat",
                frame_type=frame_type,
                processor=_processor_role(data.source),
                event_source="pipeline",
            )

    async def on_processor_setup(self, data: ProcessorSetUp) -> None:
        self.trace.record(
            "processor_setup",
            component="pipecat",
            processor=_processor_role(data.processor),
            duration_ms=(data.finished_at_ns - data.started_at_ns) / 1_000_000,
            event_source="setup",
        )


class LocalErrorObserver(ErrorObserver):
    def __init__(self, trace) -> None:
        super().__init__()
        self.trace = trace

        @self.event_handler("on_error")
        async def on_error(_observer, event):
            category = getattr(event, "category", None)
            category = getattr(category, "value", category)
            if category not in {
                "timeout",
                "permission",
                "connection",
                "io",
                "validation",
                "runtime",
            }:
                category = "unknown"
            processor_name = str(getattr(event, "processor", "")).casefold()
            processor = next(
                (
                    role
                    for role in ("llm", "stt", "tts", "input", "output")
                    if role in processor_name
                ),
                "other",
            )
            self.trace.record(
                "pipeline_error",
                component="pipecat",
                error_category=category,
                processor_usable=bool(getattr(event, "processor_usable", False)),
                processor=processor,
                event_source="error_observer",
            )
