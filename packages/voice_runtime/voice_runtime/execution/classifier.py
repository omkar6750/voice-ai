"""Provider-neutral classifier execution and context-safe result normalization."""

from __future__ import annotations

import json
from typing import Any

from pipecat.processors.aggregators.llm_context import LLMContext

from voice_runtime.contracts.cadence import (
    LEAD_CLASSIFIER_PROMPT,
    LEAD_OUTPUT_FIELDS,
    ClassifierConfig,
)
from voice_runtime.diagnostics import exception_diagnostic, provider_error_diagnostic
from voice_runtime.execution.llm_factory import build_llm_service
from voice_runtime.safe_logs import RuntimeEvent, error_category, operational_event

DEFAULT_OUTPUT_FIELDS = LEAD_OUTPUT_FIELDS
DEFAULT_RESULT = {"status": "error", "code": "classifier_unavailable"}


def _diagnostic_error(provider: str, message: str, exc: Exception | None = None) -> dict[str, Any]:
    result = dict(DEFAULT_RESULT)
    result["_diagnostic"] = (
        exception_diagnostic(
            exc,
            source="provider",
            category="provider_request_failed",
            code=f"{provider}_classifier_failed",
            message=message,
            retryable=True,
        )
        if exc is not None
        else provider_error_diagnostic(
            provider=provider, status_code=401, body={"message": message}
        )
    )
    return result


def normalize_classifier_result(
    raw: Any,
    output_fields: dict[str, list[str]] | list[str] | None = None,
    *,
    max_result_chars: int = 512,
) -> dict[str, Any]:
    """Return the fixed three labels and derived combination; strip provider padding."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return dict(DEFAULT_RESULT)
    if not isinstance(raw, dict):
        return dict(DEFAULT_RESULT)
    if raw.get("status") == "error":
        result = dict(DEFAULT_RESULT)
        if isinstance(raw.get("_diagnostic"), dict):
            result["_diagnostic"] = raw["_diagnostic"]
        return result

    result: dict[str, Any] = {}
    for field, labels in DEFAULT_OUTPUT_FIELDS.items():
        value = raw.get(field)
        if isinstance(value, dict):
            value = value.get("choice")
        if isinstance(value, str) and (not labels or value in labels):
            result[field] = value
    if len(result) != len(DEFAULT_OUTPUT_FIELDS):
        return dict(DEFAULT_RESULT)
    result["classification_key"] = "|".join(result[field] for field in DEFAULT_OUTPUT_FIELDS)
    encoded = json.dumps(result, separators=(",", ":"), ensure_ascii=False)
    if len(encoded) > max_result_chars:
        return dict(DEFAULT_RESULT)
    return result


def model_visible_result(result: dict[str, Any], max_result_chars: int = 512) -> dict[str, Any]:
    """Strip internal diagnostics before a result is inserted into Pipecat context."""
    visible = {key: value for key, value in result.items() if not key.startswith("_")}
    encoded = json.dumps(visible, separators=(",", ":"), ensure_ascii=False)
    if len(encoded) > max_result_chars:
        return dict(DEFAULT_RESULT)
    return visible


class PipecatLLMClassifierRunner:
    """One-shot classifier using Pipecat's provider adapter and LLMContext."""

    async def run(self, *, settings, config: dict[str, Any], transcript: str) -> dict[str, Any]:
        provider = config.get("provider", "groq")
        model = config.get("model", "qwen/qwen3.8-27b")
        prompt = LEAD_CLASSIFIER_PROMPT
        output_fields = DEFAULT_OUTPUT_FIELDS
        max_tokens = 256
        schema = json.dumps(output_fields, separators=(",", ":"), ensure_ascii=False)
        system_instruction = (
            f"{prompt}\nReturn only one compact JSON object. Allowed fields and labels: {schema}."
        )
        try:
            service = build_llm_service(
                settings,
                {
                    **config,
                    "model": model,
                    "temperature": 0.1,
                    "max_tokens": max_tokens,
                    "reasoning_effort": "none",
                },
                stage="classifier",
                system_instruction=system_instruction,
            )
            context = LLMContext([{"role": "user", "content": transcript}])
            raw = await service.run_inference(context, max_tokens=max_tokens)
            result = normalize_classifier_result(raw, output_fields)
            if isinstance(raw, str) and result.get("status") == "error":
                operational_event(
                    RuntimeEvent.CLASSIFIER_INVALID, level="WARNING", provider=provider
                )
            return result
        except Exception as exc:
            operational_event(
                RuntimeEvent.CLASSIFIER_FAILED,
                level="ERROR",
                provider=provider,
                error_category=error_category(exc),
            )
            return _diagnostic_error(provider, f"{provider} classifier request failed", exc)


class JevClassifierRunner:
    def __init__(self, request):
        self._request = request

    async def run(self, **kwargs) -> dict[str, Any]:
        raw = await self._request(**kwargs)
        config = kwargs.get("config") or {}
        return normalize_classifier_result(
            raw,
            config.get("output_fields"),
            max_result_chars=int(config.get("max_result_chars", 512)),
        )


async def run_selected_classifier(
    *, settings, classifier: dict[str, Any], transcript: str, jev_request
):
    classifier = ClassifierConfig.model_validate(classifier).model_dump(mode="json")
    classifier_type = classifier.get("classifier_type", "llm")
    if classifier_type == "jev":
        return await JevClassifierRunner(jev_request).run(
            settings=settings,
            config=classifier.get("jev") or {},
            transcript=transcript,
        )
    return await PipecatLLMClassifierRunner().run(
        settings=settings,
        config=classifier.get("llm") or classifier.get("model") or {},
        transcript=transcript,
    )
