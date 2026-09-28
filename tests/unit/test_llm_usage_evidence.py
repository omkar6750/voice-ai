"""Pipecat usage frames keep provider totals and cache counts intact."""

from types import SimpleNamespace

from pipecat.frames.frames import ErrorFrame, UserStartedSpeakingFrame
from pipecat.metrics.metrics import LLMTokenUsage, LLMUsageMetricsData
from pipecat.processors.frame_processor import FrameDirection
from voice_runtime.execution.exchange import ExchangeTracker
from voice_runtime.execution.observer import EvidenceObserver


def test_usage_metric_preserves_provider_total_instead_of_recomputing_it():
    observer = object.__new__(EvidenceObserver)
    llm = object()
    observer.llm = llm
    observer.tts = object()
    observer.stt = object()
    observer.metrics = {"llm": {}, "stt": {}, "tts": {}}
    usage = LLMTokenUsage(
        prompt_tokens=6,
        completion_tokens=1,
        total_tokens=8,
        cache_read_input_tokens=2,
        cache_creation_input_tokens=0,
        reasoning_tokens=1,
    )

    observer._metrics(
        llm,
        SimpleNamespace(data=[LLMUsageMetricsData(processor="gemini", value=usage)]),
    )

    assert observer.metrics["llm"] == {
        "prompt_tokens": 6,
        "completion_tokens": 1,
        "total_tokens": 8,
        "cache_read_input_tokens": 2,
        "cache_creation_input_tokens": 0,
        "reasoning_tokens": 1,
    }


def test_provider_error_frame_fails_active_operation_and_keeps_request_diagnostics():
    class Response:
        status_code = 400

        @property
        def headers(self):
            return {"x-request-id": "req-42"}

        @staticmethod
        def json():
            return {
                "error": {
                    "code": "tool_use_failed",
                    "message": "Could not parse tool call",
                    "failed_generation": "{bad-json",
                }
            }

    class ProviderError(Exception):
        response = Response()

    class Sink:
        def __init__(self):
            self.records = []

        def submit(self, record):
            self.records.append(record)

    sink = Sink()
    tracker = ExchangeTracker("run-1", sink)
    tracker.begin("caller")
    operation = tracker.start_operation("inference", "llm", provider="groq", model="test")
    llm = object()
    observer = object.__new__(EvidenceObserver)
    observer.tracker = tracker
    observer.llm, observer.stt, observer.tts = llm, object(), object()
    observer.providers = {"llm": "groq", "stt": "sarvam", "tts": "cartesia"}
    observer.models = {"llm": "test", "stt": "stt", "tts": "tts"}
    observer.llm_operation = operation
    observer.llm_text = []
    observer.function_calls = []
    observer.metrics = {"llm": {}, "stt": {}, "tts": {}}
    observer._log = None
    observer._mark = lambda *_args, **_kwargs: None
    frame = ErrorFrame(error="function generation failed", processor=llm, exception=ProviderError())

    import asyncio

    asyncio.run(
        observer.on_push_frame(
            SimpleNamespace(frame=frame, source=llm, direction=FrameDirection.DOWNSTREAM)
        )
    )

    assert observer.llm_operation is None
    assert any(
        record.get("kind") == "diagnostic"
        and record.get("metadata", {}).get("failed_generation") == "{bad-json"
        for record in sink.records
    )
    assert any(
        record.get("kind") == "span" and record.get("status") == "failed" for record in sink.records
    )


def test_turn_decisions_enter_durable_diagnostics_without_transcript_text():
    class Sink:
        def __init__(self):
            self.records = []

        def submit(self, record):
            self.records.append(record)

    sink = Sink()
    tracker = ExchangeTracker("run-1", sink)
    observer = object.__new__(EvidenceObserver)
    observer.tracker = tracker
    observer._log = None
    observer._mark = lambda *_args, **_kwargs: None

    observer.record_turn_event("user_turn_stopped", strategy="TurnAnalyzerUserTurnStopStrategy")

    diagnostic = sink.records[-1]
    assert diagnostic["kind"] == "diagnostic"
    assert diagnostic["category"] == "turn_decision"
    assert diagnostic["metadata"]["strategy"] == "TurnAnalyzerUserTurnStopStrategy"
    assert "transcript" not in diagnostic


def test_new_caller_turn_closes_previous_unfinalized_stt_operation_as_incomplete():
    class Sink:
        def __init__(self):
            self.records = []

        def submit(self, record):
            self.records.append(record)

    sink = Sink()
    tracker = ExchangeTracker("run-1", sink)
    tracker.begin("caller")
    previous_speech = tracker.start_operation("caller speech", "speech")
    previous_stt = tracker.start_operation(
        "transcription", "stt", parent_operation_id=previous_speech["operation_id"]
    )
    observer = object.__new__(EvidenceObserver)
    observer.tracker = tracker
    observer.llm = object()
    observer.stt = object()
    observer.tts = object()
    observer.providers = {"llm": "groq", "stt": "sarvam", "tts": "sarvam"}
    observer.models = {"llm": "llm", "stt": "stt", "tts": "tts"}
    observer.stt_operation = previous_stt
    observer.speech_operation = None
    observer.llm_operation = None
    observer.metrics = {"llm": {}, "stt": {}, "tts": {}}
    observer.last_speech_operation_id = None
    observer._log = None
    observer._mark = lambda *_args, **_kwargs: None

    import asyncio

    asyncio.run(
        observer.on_push_frame(
            SimpleNamespace(
                frame=UserStartedSpeakingFrame(),
                source=observer.stt,
                direction=FrameDirection.DOWNSTREAM,
            )
        )
    )

    prior_span = next(
        record
        for record in sink.records
        if record.get("kind") == "span"
        and record.get("operation_id") == previous_stt["operation_id"]
    )
    assert prior_span["status"] == "failed"
    assert prior_span["output_state"] == "failed"
    assert prior_span["attributes"]["failure_reason"] == "missing_final_transcription"
    assert any(
        record.get("kind") == "diagnostic" and record.get("code") == "final_transcription_missing"
        for record in sink.records
    )
