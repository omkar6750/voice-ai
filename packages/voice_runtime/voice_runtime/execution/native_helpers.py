"""Pure and Pipecat-local helper functions for the native runtime."""

from __future__ import annotations

import re
from typing import Any

import httpx
from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3
from pipecat.frames.frames import LLMContextFrame
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMUserAggregatorParams,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.turns.user_start import TranscriptionUserTurnStartStrategy, VADUserTurnStartStrategy
from pipecat.turns.user_stop.turn_analyzer_user_turn_stop_strategy import (
    TurnAnalyzerUserTurnStopStrategy,
)
from pipecat.turns.user_turn_strategies import UserTurnStrategies

from voice_runtime.diagnostics import exception_diagnostic, provider_error_diagnostic
from voice_runtime.execution.classifier import normalize_classifier_result
from voice_runtime.execution.exchange import ExchangeTracker
from voice_runtime.safe_logs import RuntimeEvent, error_category, operational_event

_OPENING_PLACEHOLDER = re.compile(r"{{\s*([A-Za-z0-9_.:-]+)\s*}}")


def _extract_transcript(
    context: LLMContext | None, tracker: ExchangeTracker | None = None, limit: int = 25
) -> str:
    """Extract clean dialogue exchanges from the LLM context or tracker."""
    transcript_lines: list[str] = []
    if context and hasattr(context, "messages"):
        for msg in getattr(context, "messages", []):
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role in ("user", "assistant") and content and isinstance(content, str):
                label = "Caller" if role == "user" else "Agent"
                transcript_lines.append(f"{label}: {content}")
    elif tracker and hasattr(tracker, "transcripts"):
        for t in getattr(tracker, "transcripts", []):
            label = "Caller" if getattr(t, "speaker", "") == "user" else "Agent"
            transcript_lines.append(f"{label}: {getattr(t, 'text', '')}")
    return "\n".join(transcript_lines[-limit:])


class _CallerTurnContextEventProcessor(FrameProcessor):
    """Inject durable outcomes only on a new caller turn, before LLM inference."""

    def __init__(self, deliver, context: LLMContext) -> None:
        super().__init__()
        self._deliver = deliver
        self._last_user_message_count = sum(
            1 for message in context.get_messages() if message.get("role") == "user"
        )

    async def process_frame(self, frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if direction == FrameDirection.DOWNSTREAM and isinstance(frame, LLMContextFrame):
            messages = frame.context.get_messages()
            user_message_count = sum(1 for message in messages if message.get("role") == "user")
            if user_message_count < self._last_user_message_count:
                # Flow context strategies may intentionally replace/prune history.
                self._last_user_message_count = user_message_count
            elif user_message_count > self._last_user_message_count:
                self._last_user_message_count = user_message_count
                await self._deliver(frame.context)
        await self.push_frame(frame, direction)


def render_opening(text: str, state: dict[str, Any]) -> str:
    """Render only values already exposed to the flow state."""

    def replace(match: re.Match[str]) -> str:
        value: Any = state
        for part in match.group(1).split("."):
            if not isinstance(value, dict) or part not in value:
                raise ValueError(f"Opening references unavailable variable '{match.group(1)}'")
            value = value[part]
        return "" if value is None else str(value)

    return _OPENING_PLACEHOLDER.sub(replace, text)


def _callback_api_error_result(response: httpx.Response) -> dict[str, str]:
    """Convert non-2xx callback API responses into a model-visible tool failure."""
    try:
        body = response.json()
    except ValueError:
        body = None
    detail = body.get("detail") if isinstance(body, dict) else None
    if isinstance(detail, str) and detail.strip():
        message = detail.strip()[:500]
    else:
        message = f"Callback scheduling request failed (HTTP {response.status_code})"
    return {"status": "error", "error": message}


def _callback_api_success_result(response: httpx.Response) -> dict[str, Any]:
    """Require successful HTTP status and an object result from the callback API."""
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        return _callback_api_error_result(exc.response)
    try:
        result = response.json()
    except ValueError:
        return {"status": "error", "error": "Callback API returned invalid JSON"}
    if not isinstance(result, dict):
        return {"status": "error", "error": "Callback API returned an invalid result"}
    return result


def whatsapp_template_header_component(header: dict[str, Any] | None) -> dict | None:
    """Build Meta's template header component from a pinned provider reference."""
    if header is None:
        return None
    if not isinstance(header, dict):
        raise ValueError("WhatsApp template header configuration is invalid")
    header_type = {"IMAGE": "image", "VIDEO": "video", "DOCUMENT": "document"}.get(
        header.get("format")
    )
    media_id = header.get("media_id")
    if not header_type or not isinstance(media_id, str) or not media_id:
        raise ValueError("WhatsApp template header configuration is invalid")
    return {
        "type": "header",
        "parameters": [{"type": header_type, header_type: {"id": media_id}}],
    }


def build_whatsapp_template_payload(
    *,
    destination: str,
    template_name: str,
    language: str,
    header: dict[str, Any] | None,
    parameter_mappings: dict[str, str],
    arguments: dict[str, Any],
    caller_name: str,
) -> dict:
    """Build the provider request without resolving or rewriting media references."""
    components = []
    header_component = whatsapp_template_header_component(header)
    if header_component is not None:
        components.append(header_component)
    if arguments.get("components"):
        components.extend(arguments["components"])
    elif parameter_mappings:
        body_params = [
            {"type": "text", "text": str(arguments[argument])[:1024]}
            for index, argument in sorted(parameter_mappings.items(), key=lambda item: int(item[0]))
            if arguments.get(argument) is not None
        ]
        components.append({"type": "body", "parameters": body_params})
    else:
        body_params = [{"type": "text", "text": caller_name}]
        if arguments.get("message"):
            body_params.append(
                {"type": "text", "text": " ".join(str(arguments["message"]).split())[:1024]}
            )
        for key in sorted(arguments):
            if key.startswith("param_") and key != "param_1":
                body_params.append({"type": "text", "text": str(arguments[key])[:1024]})
        components.append({"type": "body", "parameters": body_params})
    return {
        "messaging_product": "whatsapp",
        "to": destination,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language or "en"},
            "components": components,
        },
    }


def trim_classifier_result(res: dict) -> dict:
    """Backward-compatible name for the context-safe classifier normalizer."""
    return normalize_classifier_result(res)


def _retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def _provider_body(response: httpx.Response) -> dict | str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:500]
    return body if isinstance(body, dict) else str(body)


def build_user_aggregator_params(snapshot: dict, vad) -> LLMUserAggregatorParams:
    """Apply explicit Silero start and Smart Turn v3 stop strategies."""
    limits = snapshot["call_limits"]
    stop_strategies = [TurnAnalyzerUserTurnStopStrategy(turn_analyzer=LocalSmartTurnAnalyzerV3())]
    strategies = UserTurnStrategies(stop=stop_strategies)
    if not limits["interruptions_enabled"]:
        strategies = UserTurnStrategies(
            start=[
                VADUserTurnStartStrategy(enable_interruptions=False),
                TranscriptionUserTurnStartStrategy(enable_interruptions=False),
            ],
            stop=stop_strategies,
        )
    return LLMUserAggregatorParams(
        vad_analyzer=vad,
        user_turn_strategies=strategies,
        user_idle_timeout=limits["idle_timeout_secs"],
    )


async def run_jev_classification(
    api_key: str,
    transcript: str,
    questions: dict,
    model: str = "jev-latest",
    api_url: str = "https://api.typesafe.ai/v1/systemone",
) -> dict:
    """Execute TypeSafe AI Jev System One multi-choice classification."""
    jev_payload = {
        "model": model,
        "state": transcript,
        "questions": questions,
    }
    if not api_key:
        operational_event(RuntimeEvent.CREDENTIALS_MISSING, level="WARNING", provider="jev")
        return {
            "status": "error",
            "error": "JEV API key is not configured",
            "_diagnostic": provider_error_diagnostic(
                provider="jev", status_code=401, body={"message": "API key is not configured"}
            ),
        }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                api_url,
                json=jev_payload,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                answers = data.get("answers", data)
                normalized: dict[str, Any] = {}
                for key, val in answers.items():
                    if isinstance(val, dict):
                        normalized[key] = val
                    elif isinstance(val, str):
                        normalized[key] = {"choice": val, "confidence": 1.0}
                    else:
                        normalized[key] = {"choice": str(val), "confidence": 0.5}
                return normalized
            operational_event(
                RuntimeEvent.PROVIDER_FAILED,
                level="ERROR",
                provider="jev",
                http_status=resp.status_code,
            )
            try:
                body = resp.json()
            except Exception:
                body = resp.text[:500]
            return {
                "status": "error",
                "error": f"JEV provider returned HTTP {resp.status_code}",
                "_diagnostic": provider_error_diagnostic(
                    provider="jev",
                    status_code=resp.status_code,
                    body=body,
                    request_id=resp.headers.get("x-request-id") or resp.headers.get("request-id"),
                    retry_after_seconds=_retry_after(resp.headers.get("retry-after")),
                ),
            }
    except Exception as exc:
        operational_event(
            RuntimeEvent.PROVIDER_FAILED,
            level="ERROR",
            provider="jev",
            error_category=error_category(exc),
        )
        return {
            "status": "error",
            "error": "JEV provider request failed",
            "_diagnostic": exception_diagnostic(
                exc,
                source="provider",
                category="provider_request_failed",
                code="jev_request_failed",
                message="Jev provider request failed",
                retryable=True,
            ),
        }
