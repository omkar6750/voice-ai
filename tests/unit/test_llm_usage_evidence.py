"""Pipecat usage frames keep provider totals and cache counts intact."""

from types import SimpleNamespace

from pipecat.metrics.metrics import LLMTokenUsage, LLMUsageMetricsData
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
