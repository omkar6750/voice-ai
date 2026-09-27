"""DB-snapshot-driven Pipecat host for one voice call.

Transport-neutral: the caller injects a ready Pipecat BaseTransport.
This deliberately does not import the protected standalone demo.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.flows import ContextStrategy, ContextStrategyConfig, FlowManager, NodeConfig
from pipecat.flows.types import FlowsFunctionSchema
from pipecat.frames.frames import FunctionCallResultProperties, TTSSpeakFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.google.llm import GoogleLLMService
from pipecat.services.groq.llm import GroqLLMService
from pipecat.services.sarvam.stt import SarvamSTTService
from pipecat.services.sarvam.tts import SarvamTTSService
from pipecat.workers.runner import WorkerRunner

from voice_runtime.call_capture import CallCapture
from voice_runtime.contracts import is_registered_handler
from voice_runtime.diagnostics import (
    exception_diagnostic,
    provider_error_diagnostic,
    text_error_diagnostic,
)
from voice_runtime.execution.contact_context import sanitize_contact_variables
from voice_runtime.execution.exchange import ExchangeTracker, bind_transcripts
from voice_runtime.execution.observer import EvidenceObserver
from voice_runtime.execution.temporal import resolve_local_time_context
from voice_runtime.telephony.base import CallState


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


_OPENING_PLACEHOLDER = re.compile(r"{{\s*([A-Za-z0-9_.:-]+)\s*}}")


def render_opening(text: str, state: dict[str, Any]) -> str:
    """Render only values already exposed to the flow state."""

    def replace(match: re.Match[str]) -> str:
        value: Any = state
        for part in match.group(1).split("."):
            if not isinstance(value, dict) or part not in value:
                raise ValueError(
                    f"Opening references unavailable variable '{match.group(1)}'"
                )
            value = value[part]
        return "" if value is None else str(value)

    return _OPENING_PLACEHOLDER.sub(replace, text)


def trim_classifier_result(res: dict) -> dict:
    """Schema-agnostic trimmer for classification output matching demo_call.py compact format."""
    if not isinstance(res, dict):
        return {"result": str(res)}
    trimmed: dict[str, Any] = {}
    for k, v in res.items():
        if isinstance(v, dict):
            choice = v.get("choice")
            if choice is not None:
                trimmed[k] = choice
            probs = v.get("probabilities")
            if isinstance(probs, dict):
                for pk, pv in probs.items():
                    if isinstance(pv, (int, float)) and pv >= 0.1:
                        trimmed[f"{k}_{pk}"] = round(float(pv), 2)
            elif "confidence" in v and v["confidence"] is not None:
                trimmed[f"{k}_conf"] = round(float(v["confidence"]), 2)
        else:
            trimmed[k] = v
    return trimmed


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


def build_speech_services(settings, snapshot: dict, sample_rate: int):
    """Build STT/TTS services from the resolved snapshot's exact selections."""

    stt_config = snapshot["stt"]
    if stt_config["provider"] != "sarvam":
        raise ValueError(f"Unsupported STT provider: {stt_config['provider']}")
    stt = SarvamSTTService(
        api_key=settings.sarvam_api_key,
        settings=SarvamSTTService.Settings(model=stt_config["model"]),
        sample_rate=sample_rate,
    )

    tts_config = snapshot["tts"]
    if tts_config["provider"] == "sarvam":
        tts = SarvamTTSService(
            api_key=settings.sarvam_api_key,
            settings=SarvamTTSService.Settings(
                model=tts_config["model"],
                voice=tts_config["voice"],
                language=tts_config["language"],
                pace=tts_config["pace"],
            ),
            sample_rate=sample_rate,
        )
    elif tts_config["provider"] == "cartesia":
        tts = CartesiaTTSService(
            api_key=settings.cartesia_api_key,
            settings=CartesiaTTSService.Settings(
                model=tts_config["model"],
                voice=tts_config["voice"],
                language=tts_config["language"],
            ),
            sample_rate=sample_rate,
            encoding="pcm_s16le",
            container="raw",
        )
    else:
        raise ValueError(f"Unsupported TTS provider: {tts_config['provider']}")
    return stt, tts


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
        logger.warning("JEV API key not configured on runtime")
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
            logger.error("JEV System One HTTP {}", resp.status_code)
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
        logger.error("JEV System One API error: {}", exc)
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


async def run_llm_classification(
    api_key: str,
    transcript: str,
    prompt: str = "Classify the supplied conversation using only observed evidence.",
    model: str = "llama-3.3-70b-versatile",
) -> dict:
    """Execute LLM categorization with compact JSON return."""
    if not api_key:
        logger.warning("Groq API key not configured for LLM classification")
        return {
            "status": "error",
            "error": "Groq API key is not configured",
            "_diagnostic": provider_error_diagnostic(
                provider="groq", status_code=401, body={"message": "API key is not configured"}
            ),
        }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                json={
                    "model": model,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                f"{prompt}\nReturn your evaluation strictly as a valid, compact JSON object."
                            ),
                        },
                        {"role": "user", "content": f"Dialogue Transcript:\n{transcript}"},
                    ],
                    "temperature": 0.1,
                    "response_format": {"type": "json_object"},
                },
                headers={"Authorization": f"Bearer {api_key}"},
            )
            if resp.status_code == 200:
                raw_data = json.loads(resp.json()["choices"][0]["message"]["content"])
                return raw_data if isinstance(raw_data, dict) else {"result": raw_data}
            logger.error("LLM classification HTTP {}", resp.status_code)
            try:
                body = resp.json()
            except Exception:
                body = resp.text[:500]
            return {
                "status": "error",
                "error": f"LLM provider returned HTTP {resp.status_code}",
                "_diagnostic": provider_error_diagnostic(
                    provider="groq",
                    status_code=resp.status_code,
                    body=body,
                    request_id=resp.headers.get("x-request-id") or resp.headers.get("request-id"),
                    retry_after_seconds=_retry_after(resp.headers.get("retry-after")),
                ),
            }
    except Exception as exc:
        logger.error("LLM classification error: {}", exc)
        return {
            "status": "error",
            "error": "LLM classifier provider request failed",
            "_diagnostic": exception_diagnostic(
                exc,
                source="provider",
                category="provider_request_failed",
                code="groq_request_failed",
                message="Groq provider request failed",
                retryable=True,
            ),
        }


def _parse_spoken_callback_time(phrase: str) -> datetime:
    """Parse common spoken natural language date and time phrases into aware UTC datetime."""
    phrase_lower = phrase.lower()
    now = datetime.now(UTC)
    if "hour" in phrase_lower:
        m = re.search(r"(\d+)\s*hour", phrase_lower)
        if m:
            return now + timedelta(hours=int(m.group(1)))
    target_date = now.date()
    if "tomorrow" in phrase_lower:
        target_date += timedelta(days=1)
    elif "day after tomorrow" in phrase_lower:
        target_date += timedelta(days=2)
    elif "next week" in phrase_lower:
        target_date += timedelta(days=7)
    else:
        weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        for idx, day in enumerate(weekdays):
            if day in phrase_lower:
                days_ahead = (idx - target_date.weekday()) % 7
                if days_ahead == 0:
                    days_ahead = 7
                target_date += timedelta(days=days_ahead)
                break
    hour, minute = 10, 0
    if "morning" in phrase_lower:
        hour, minute = 10, 0
    elif "afternoon" in phrase_lower:
        hour, minute = 14, 0
    elif "evening" in phrase_lower:
        hour, minute = 17, 0
    elif "night" in phrase_lower:
        hour, minute = 19, 0

    match = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", phrase_lower)
    if match:
        h = int(match.group(1))
        m = int(match.group(2)) if match.group(2) else 0
        ampm = match.group(3)
        if ampm == "pm" and h < 12:
            h += 12
        elif ampm == "am" and h == 12:
            h = 0
        elif not ampm and h < 8:
            h += 12
        if 0 <= h <= 23 and 0 <= m <= 59:
            hour, minute = h, m

    due = datetime(target_date.year, target_date.month, target_date.day, hour, minute, tzinfo=UTC)
    if due <= now:
        due += timedelta(days=1)
    return due


class TracedFlowManager(FlowManager):
    def __init__(
        self,
        *,
        tracker: ExchangeTracker,
        bindings: dict,
        observer: EvidenceObserver,
        context: LLMContext,
        classifier_runner: Callable[[str, str], Awaitable[tuple[str, dict[str, str]] | None]],
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.tracker = tracker
        self.bindings = bindings
        self.observer = observer
        self._context_for_evidence = context
        self._classifier_runner = classifier_runner
        self._transition_tool_id: str | None = None

    def _context_message_index(self) -> int | None:
        messages = self._context_for_evidence.get_messages()
        return len(messages) - 1 if messages else None

    async def _set_node(self, node_id: str, node_config: NodeConfig) -> None:
        classifier_messages: list[dict[str, str]] = []
        current_node = self.current_node
        if current_node and current_node != node_id:
            classifier = await self._classifier_runner("exit", current_node)
            if classifier is not None:
                _, message = classifier
                classifier_messages.append(message)
        classifier = await self._classifier_runner("entry", node_id)
        if classifier is not None:
            _, message = classifier
            classifier_messages.append(message)
        if classifier_messages:
            node_config = dict(node_config)
            node_config["task_messages"] = [
                *node_config.get("task_messages", []),
                *classifier_messages,
            ]
        await super()._set_node(node_id, node_config)
        self.tracker.start_visit(node_id, self._transition_tool_id)
        self._transition_tool_id = None

    async def _create_transition_func(self, name, handler):
        execute = await super()._create_transition_func(name, handler)

        async def traced(params):
            binding = self.bindings[name]
            invocation_id = self.tracker.start_tool(
                name,
                binding["version_id"],
                params.tool_call_id,
                dict(params.arguments),
                self.observer.function_operations.get(params.tool_call_id)
                or (
                    self.observer.llm_operation["operation_id"]
                    if self.observer.llm_operation
                    else None
                ),
            )
            final_result: Any = None
            final_sent = False
            original_callback = params.result_callback

            async def result_callback(result, *, properties=None):
                nonlocal final_result, final_sent
                is_final = properties is None or properties.is_final
                connection_id = None
                provider_message_id = None
                diagnostic = None
                if isinstance(result, dict):
                    result = dict(result)
                    connection_id = result.pop("_connection_id", None)
                    provider_message_id = result.pop("_provider_message_id", None)
                    diagnostic = result.pop("_diagnostic", None)
                    if diagnostic is None and result.get("status") == "error":
                        diagnostic = exception_diagnostic(
                            RuntimeError(str(result.get("error", "Tool execution failed"))),
                            category="tool_failure",
                            code="tool_error",
                            message=f"Tool {name} failed",
                        )
                if isinstance(diagnostic, dict):
                    self.tracker.diagnostic(**diagnostic)
                result_id = self.tracker.tool_result(invocation_id, result, is_final=is_final)
                if (
                    name == "change_node"
                    and is_final
                    and isinstance(result, dict)
                    and result.get("status") == "ok"
                ):
                    self._transition_tool_id = invocation_id
                result_properties = properties or FunctionCallResultProperties(is_final=is_final)
                previous_context_callback = result_properties.on_context_updated

                async def context_updated() -> None:
                    self.tracker.context_updated(
                        invocation_id,
                        result_id,
                        context_message_index=self._context_message_index(),
                    )
                    if previous_context_callback is not None:
                        await previous_context_callback()

                result_properties = replace(
                    result_properties, on_context_updated=context_updated
                )
                await original_callback(result, properties=result_properties)
                if is_final:
                    final_result, final_sent = result, True
                    self.tracker.end_tool(
                        invocation_id,
                        "failed"
                        if isinstance(result, dict) and result.get("status") == "error"
                        else "completed",
                        result,
                        connection_id=connection_id,
                        provider_message_id=provider_message_id,
                    )

            try:
                await execute(replace(params, result_callback=result_callback))
            finally:
                if not final_sent and not self.tracker.tool_was_ended(invocation_id):
                    self.tracker.end_tool(
                        invocation_id, "failed", {"error": "No final tool result"}
                    )
            return final_result

        return traced


class NativePipelineHost:
    def __init__(self, run_id: str, recordings_dir: Path, settings) -> None:
        self.run_id, self.directory, self.settings = run_id, recordings_dir / run_id, settings
        self.worker = self.flow = self.capture = self.observer = None
        self.runner_task: asyncio.Task | None = None
        self.ready = asyncio.Event()
        self.errors: list[str] = []
        self._call_hung_up: bool = False
        self._termination_diagnostic_recorded = False
        self._end_task: asyncio.Task | None = None
        self.tracker: ExchangeTracker | None = None
        self._nodes: dict[str, dict] = {}
        self._snapshot: dict = {}
        self._verbatim_opening: str | None = None

    def _node(self, key: str) -> NodeConfig:
        node = self._nodes[key]
        flow = self._snapshot["flow"]
        role_message = node.get("role_prompt")
        if key == flow.get("initial_node") and not role_message:
            role_message = self._snapshot.get("system_prompt", "")
        if "initial_node" not in flow and not role_message:
            # Compatibility for pre-Pipecat snapshots used by older evidence tests.
            role_message = node.get("prompt", "")
        task_messages = []
        if node.get("prompt"):
            task_messages.append({"role": "user", "content": node["prompt"]})
        if node.get("terminal"):
            task_messages.append(
                {
                    "role": "user",
                    "content": (
                        "Deliver the terminal response now. Do not restart the conversation, "
                        "greet the caller, ask discovery questions, or continue the flow."
                    ),
                }
            )
        bindings = self._snapshot["_resolved"]["tools"]
        functions = []
        for name in node["tool_bindings"]:
            tool = bindings[name]["definition"]
            parameters = tool["parameters"]
            functions.append(
                FlowsFunctionSchema(
                    name=name,
                    description=tool["description"],
                    properties=parameters.get("properties", {}),
                    required=parameters.get("required", []),
                    handler=self._handler(name),
                )
            )
        return NodeConfig(
            name=key,
            role_message=role_message or "",
            task_messages=task_messages,
            functions=functions,
            respond_immediately=node["respond_immediately"],
            context_strategy=ContextStrategyConfig(
                strategy=ContextStrategy(node.get("context_strategy", "append"))
            ),
        )

    async def _run_node_classifier(
        self, phase: str, node_key: str
    ) -> tuple[str, dict[str, str]] | None:
        """Run one configured node classifier and return its context message."""
        classifier_cfg = self._snapshot.get("classifier", {})
        if not classifier_cfg.get("enabled", True):
            return None
        configured_nodes = classifier_cfg.get("node_entries" if phase == "entry" else "node_exits", [])
        if node_key not in configured_nodes or self.tracker is None:
            return None

        classifier_type = classifier_cfg.get("classifier_type", "llm")
        transcript = _extract_transcript(getattr(self, "context", None), self.tracker)
        if classifier_type == "jev":
            jev_cfg = classifier_cfg.get("jev", {})
            provider, model = "typesafe", jev_cfg.get("model", "jev-latest")
        else:
            llm_cfg = classifier_cfg.get("model", {})
            provider, model = llm_cfg.get("provider", "groq"), llm_cfg.get(
                "model", "llama-3.3-70b-versatile"
            )

        operation = self.tracker.start_classifier(
            phase=phase,
            node_key=node_key,
            classifier_type=classifier_type,
            provider=provider,
            model=model,
            transcript=transcript,
        )
        result: dict[str, Any]
        error: str | None = None
        try:
            if classifier_type == "jev":
                jev_cfg = classifier_cfg.get("jev", {})
                questions = jev_cfg.get("questions") or {}
                if not questions:
                    from voice_runtime.contracts.cadence import default_jev_questions

                    questions = {key: value.model_dump() for key, value in default_jev_questions().items()}
                jev_key = getattr(self.settings, "jev_api_key", None) or os.getenv(
                    "VOICE_JEV_API_KEY", ""
                )
                raw_result = await run_jev_classification(
                    api_key=jev_key,
                    transcript=transcript,
                    questions=questions,
                    model=model,
                    api_url=jev_cfg.get("api_url", "https://api.typesafe.ai/v1/systemone"),
                )
            elif provider == "groq":
                groq_key = getattr(self.settings, "groq_api_key", None) or os.getenv(
                    "VOICE_GROQ_API_KEY", ""
                )
                raw_result = await run_llm_classification(
                    api_key=groq_key,
                    transcript=transcript,
                    prompt=classifier_cfg.get(
                        "prompt", "Classify the supplied conversation using only observed evidence."
                    ),
                    model=model,
                )
            else:
                raw_result = {
                    "status": "error",
                    "error": f"Unsupported classifier LLM provider: {provider}",
                }
            result = trim_classifier_result(raw_result)
            raw_diagnostic = raw_result.get("_diagnostic") if isinstance(raw_result, dict) else None
            if isinstance(raw_diagnostic, dict):
                self.tracker.diagnostic(**raw_diagnostic)
            if result.get("status") == "error":
                error = str(result.get("error", "Classifier failed"))
        except Exception:
            logger.exception("{} classifier failed for node {}", phase, node_key)
            result = {"status": "error", "error": "Classifier execution failed"}
            error = str(result["error"])

        status = "failed" if error else "completed"
        result_id, message = self.tracker.finish_classifier(
            operation, status, result, error=error
        )
        return result_id, message

    async def _whatsapp_runtime_config(
        self,
        *,
        connection_id: str | None = None,
        local_media_id: str | None = None,
    ) -> tuple[str, str, str | None, str, str | None, str | None]:
        """Resolve WhatsApp credentials and an optional catalog media record."""
        access_token = getattr(self.settings, "whatsapp_access_token", None) or os.getenv(
            "VOICE_WHATSAPP_ACCESS_TOKEN", ""
        )
        phone_number_id = getattr(self.settings, "whatsapp_phone_number_id", None) or os.getenv(
            "VOICE_WHATSAPP_PHONE_NUMBER_ID", ""
        )
        connection_id = None
        api_version = "v21.0"
        header_media_id = None
        header_media_type = None
        if phone_number_id:
            try:
                from sqlalchemy import select
                from voice_api.db.session import SessionFactory
                from voice_api.models import (
                    IntegrationConnection,
                    IntegrationMedia,
                    IntegrationSecret,
                )
                from voice_api.services.vault_service import CredentialVault

                async with SessionFactory() as session:
                    query = select(IntegrationConnection).where(
                        IntegrationConnection.provider == "whatsapp",
                        IntegrationConnection.enabled.is_(True),
                    )
                    if connection_id:
                        query = query.where(IntegrationConnection.id == connection_id)
                    rows = (await session.scalars(query)).all()
                    for row in rows:
                        if connection_id or str(row.config.get("phone_number_id", "")) == str(
                            phone_number_id
                        ):
                            connection_id = str(row.id)
                            phone_number_id = str(row.config.get("phone_number_id") or phone_number_id)
                            api_version = str(row.config.get("api_version") or api_version)
                            if local_media_id:
                                media = await session.scalar(
                                    select(IntegrationMedia).where(
                                        IntegrationMedia.id == local_media_id,
                                        IntegrationMedia.connection_id == row.id,
                                        IntegrationMedia.status == "available",
                                    )
                                )
                                header_media_id = (
                                    media.provider_media_id if media is not None else None
                                )
                                header_media_type = media.media_type if media is not None else None
                            if not access_token:
                                secret = await session.scalar(
                                    select(IntegrationSecret).where(
                                        IntegrationSecret.connection_id == row.id,
                                        IntegrationSecret.name == "access_token",
                                    )
                                )
                                if secret is not None:
                                    try:
                                        access_token = CredentialVault.from_env().decrypt(
                                            secret.ciphertext, secret.key_id
                                        )
                                    except Exception as exc:
                                        logger.warning(
                                            "Could not decrypt stored WhatsApp token: {}", exc
                                        )
                            break
            except Exception as exc:
                logger.warning("Could not resolve WhatsApp integration metadata: {}", exc)
        return (
            access_token,
            phone_number_id,
            connection_id,
            api_version,
            header_media_id,
            header_media_type,
        )

    def _handler(self, name: str):
        async def handle(args: dict, _manager: FlowManager):
            if name == "change_node":
                target = args.get("node")
                source = self.flow.current_node
                if target not in self._nodes[source]["transitions"]:
                    return {"status": "error", "error": "Transition is not allowed"}
                return {"status": "ok", "node": target}, self._node(target)
            if name == "end_call":
                self._call_hung_up = True
                self.tracker.diagnostic(
                    severity="info",
                    category="call_termination",
                    source="call",
                    code="agent_hangup",
                    message="Agent requested call termination",
                )
                self._end_task = asyncio.create_task(self.worker.cancel())
                return {"status": "ok"}
            if name == "check_whatsapp_window":
                contact = (
                    self._snapshot.get("_resolved", {}).get("contact")
                    or self._snapshot.get("contact_snapshot")
                    or {}
                )
                raw_phone = (
                    args.get("to")
                    or contact.get("phone_number")
                    or contact.get("phone_e164")
                    or self._snapshot.get("target_snapshot", "")
                )
                recipient = re.sub(r"[^\d]", "", raw_phone or "")
                if not recipient:
                    return {"status": "error", "error": "No valid phone number for contact"}

                cutoff = datetime.now(UTC) - timedelta(hours=24)
                has_inbound = False
                try:
                    from sqlalchemy import select
                    from voice_api.db.session import SessionFactory
                    from voice_api.models import InboundWebhookMessage

                    async with SessionFactory() as db_session:
                        inbound_row = await db_session.scalar(
                            select(InboundWebhookMessage)
                            .where(
                                InboundWebhookMessage.sender_phone == recipient,
                                InboundWebhookMessage.received_at >= cutoff,
                            )
                            .order_by(InboundWebhookMessage.received_at.desc())
                        )
                        if inbound_row is not None:
                            has_inbound = True
                except Exception as exc:
                    logger.warning("Failed checking inbound WhatsApp messages in DB: {}", exc)

                return {
                    "status": "ok",
                    "window_open": has_inbound,
                    "recipient": recipient,
                    "reason": "Customer service window open"
                    if has_inbound
                    else "Window closed (no inbound message from contact in last 24 hours; template required)",
                }
            if name == "send_whatsapp_message":
                contact = (
                    self._snapshot.get("_resolved", {}).get("contact")
                    or self._snapshot.get("contact_snapshot")
                    or {}
                )
                raw_phone = (
                    args.get("to")
                    or contact.get("phone_number")
                    or contact.get("phone_e164")
                    or self._snapshot.get("target_snapshot", "")
                )
                recipient = re.sub(r"[^\d]", "", raw_phone)
                if not recipient:
                    return {"status": "error", "error": "No valid phone number for contact"}

                # Check if contact sent an inbound WhatsApp message within the last 24 hours
                cutoff = datetime.now(UTC) - timedelta(hours=24)
                has_inbound = False
                try:
                    from sqlalchemy import select
                    from voice_api.db.session import SessionFactory
                    from voice_api.models import InboundWebhookMessage

                    async with SessionFactory() as db_session:
                        inbound_row = await db_session.scalar(
                            select(InboundWebhookMessage)
                            .where(
                                InboundWebhookMessage.sender_phone == recipient,
                                InboundWebhookMessage.received_at >= cutoff,
                            )
                            .order_by(InboundWebhookMessage.received_at.desc())
                        )
                        if inbound_row is not None:
                            has_inbound = True
                except Exception as exc:
                    logger.warning("Failed checking inbound WhatsApp messages in DB: {}", exc)

                if not has_inbound:
                    return {
                        "status": "error",
                        "error": "Customer service window is closed (no inbound WhatsApp message received from contact in the last 24 hours). Meta requires an approved template outside this window.",
                    }

                text = (args.get("text") or args.get("message") or "").strip()
                if not text:
                    return {"status": "error", "error": "Message text cannot be empty"}

                (
                    access_token,
                    phone_number_id,
                    connection_id,
                    api_version,
                    _db_header_media_id,
                    _db_header_media_type,
                ) = await self._whatsapp_runtime_config()
                if not access_token or not phone_number_id:
                    logger.warning(
                        "WhatsApp credentials not configured on runtime; failing tool cleanly"
                    )
                    return {
                        "status": "error",
                        "error": "WhatsApp credentials not configured on runtime",
                        "_diagnostic": provider_error_diagnostic(
                            provider="whatsapp",
                            status_code=401,
                            body={"message": "API key is not configured"},
                        ),
                    }

                payload = {
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": recipient,
                    "type": "text",
                    "text": {"body": text, "preview_url": False},
                }
                try:
                    logger.info("WHATSAPP sending direct message to {}", recipient)
                    async with httpx.AsyncClient(timeout=10) as client:
                        resp = await client.post(
                            f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages",
                            json=payload,
                            headers={"Authorization": f"Bearer {access_token}"},
                        )
                        if resp.status_code >= 400:
                            logger.error(
                                "WhatsApp API error: {} {}", resp.status_code, resp.text[:300]
                            )
                            return {
                                "status": "error",
                                "error": f"WhatsApp API returned HTTP {resp.status_code}",
                                "_diagnostic": provider_error_diagnostic(
                                    provider="whatsapp",
                                    status_code=resp.status_code,
                                    body=_provider_body(resp),
                                    request_id=resp.headers.get("x-request-id")
                                    or resp.headers.get("request-id"),
                                    retry_after_seconds=_retry_after(
                                        resp.headers.get("retry-after")
                                    ),
                                ),
                            }
                        data = resp.json()
                        msg_id = (data.get("messages") or [{}])[0].get("id", "unknown")
                        logger.info("WhatsApp direct message sent successfully: msg_id={}", msg_id)
                        return {
                            "status": "ok",
                            "message_id": msg_id,
                            "_connection_id": connection_id,
                            "_provider_message_id": msg_id,
                        }
                except Exception as exc:
                    logger.error("WhatsApp direct message exception: {}", exc)
                    return {
                        "status": "error",
                        "error": "WhatsApp request failed",
                        "_diagnostic": exception_diagnostic(
                            exc,
                            source="provider",
                            category="provider_request_failed",
                            code="whatsapp_request_failed",
                            message="WhatsApp provider request failed",
                            retryable=True,
                        ),
                    }

            if name.startswith("whatsapp_template_"):
                tool_definition = (
                    self._snapshot.get("_resolved", {})
                    .get("tools", {})
                    .get(name, {})
                    .get("definition", {})
                )
                whatsapp_config = tool_definition.get("whatsapp")
                if not isinstance(whatsapp_config, dict):
                    return {
                        "status": "error",
                        "error": "WhatsApp template tool is missing account configuration",
                        "_diagnostic": exception_diagnostic(
                            ValueError("missing WhatsApp template configuration"),
                            source="runtime",
                            category="tool_configuration",
                            code="whatsapp_tool_unconfigured",
                            message="WhatsApp template tool is not configured",
                            retryable=False,
                        ),
                    }
                local_media_id = whatsapp_config.get("header_media_id")
                (
                    access_token,
                    phone_number_id,
                    connection_id,
                    api_version,
                    db_header_media_id,
                    db_header_media_type,
                ) = await self._whatsapp_runtime_config(
                    connection_id=whatsapp_config.get("connection_id"),
                    local_media_id=local_media_id,
                )
                if not access_token or not phone_number_id:
                    logger.warning(
                        "WhatsApp credentials not configured on runtime; failing tool cleanly"
                    )
                    return {
                        "status": "error",
                        "error": "WhatsApp credentials not configured on runtime",
                        "_diagnostic": provider_error_diagnostic(
                            provider="whatsapp",
                            status_code=401,
                            body={"message": "API key is not configured"},
                        ),
                    }
                if local_media_id and not db_header_media_id:
                    return {
                        "status": "error",
                        "error": "Configured WhatsApp media is unavailable",
                        "_diagnostic": exception_diagnostic(
                            ValueError("configured WhatsApp media is unavailable"),
                            source="runtime",
                            category="tool_configuration",
                            code="whatsapp_media_unavailable",
                            message="Configured WhatsApp media is unavailable",
                            retryable=False,
                        ),
                    }

                contact = (
                    self._snapshot.get("_resolved", {}).get("contact")
                    or self._snapshot.get("contact_snapshot")
                    or {}
                )
                raw_phone = (
                    args.get("to")
                    or contact.get("phone_number")
                    or contact.get("phone_e164")
                    or self._snapshot.get("target_snapshot", "")
                )
                recipient = re.sub(r"[^\d]", "", raw_phone)
                if not recipient:
                    logger.warning("No recipient phone number available for WhatsApp dispatch")
                    return {"status": "error", "error": "No valid phone number for contact"}

                caller_name = (args.get("caller_name") or contact.get("name") or "there").strip()
                template_name = str(whatsapp_config.get("template_name") or "").strip()
                if not template_name:
                    return {
                        "status": "error",
                        "error": "WhatsApp template name is not configured",
                        "_diagnostic": exception_diagnostic(
                            ValueError("missing WhatsApp template name"),
                            source="runtime",
                            category="tool_configuration",
                            code="whatsapp_template_unconfigured",
                            message="WhatsApp template name is not configured",
                            retryable=False,
                        ),
                    }
                header_media_id = db_header_media_id

                summary = f"Thank you for speaking with Northstar Software Studio, {caller_name}! We have prepared your custom development overview and pricing catalog."
                if name == "send_followup" and args.get("message"):
                    summary = args["message"]
                elif args.get("message"):
                    summary = args["message"]

                components = []
                if header_media_id:
                    header_type = db_header_media_type or "image"
                    components.append(
                        {
                            "type": "header",
                            "parameters": [
                                {
                                    "type": header_type,
                                    header_type: {"id": header_media_id},
                                }
                            ],
                        }
                    )
                if args.get("components"):
                    components.extend(args["components"])
                else:
                    mappings = whatsapp_config.get("parameter_mappings") or {}
                    if mappings:
                        body_params = [
                            {"type": "text", "text": str(args[argument])[:1024]}
                            for index, argument in sorted(
                                mappings.items(), key=lambda item: int(item[0])
                            )
                            if args.get(argument) is not None
                        ]
                    else:
                        body_params = [{"type": "text", "text": caller_name}]
                        if args.get("message"):
                            body_params.append(
                                {"type": "text", "text": " ".join(summary.split())[:1024]}
                            )
                        for k in sorted(args.keys()):
                            if k.startswith("param_") and k != "param_1":
                                body_params.append(
                                    {"type": "text", "text": str(args[k])[:1024]}
                                )
                    components.append({"type": "body", "parameters": body_params})

                template_lang = str(whatsapp_config.get("language") or "en")
                if len(template_lang) > 2 and "_" in template_lang:
                    pass
                elif len(template_lang) == 2:
                    pass
                else:
                    template_lang = "en"

                payload = {
                    "messaging_product": "whatsapp",
                    "to": recipient,
                    "type": "template",
                    "template": {
                        "name": template_name,
                        "language": {"code": template_lang},
                        "components": components,
                    },
                }

                try:
                    logger.info("WHATSAPP sending template '{}' to {}", template_name, recipient)
                    async with httpx.AsyncClient(timeout=10) as client:
                        resp = await client.post(
                            f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages",
                            json=payload,
                            headers={"Authorization": f"Bearer {access_token}"},
                        )
                        if resp.status_code >= 400:
                            logger.error(
                                "WhatsApp API error: {} {}", resp.status_code, resp.text[:300]
                            )
                            return {
                                "status": "error",
                                "error": f"WhatsApp API returned HTTP {resp.status_code}",
                                "_diagnostic": provider_error_diagnostic(
                                    provider="whatsapp",
                                    status_code=resp.status_code,
                                    body=_provider_body(resp),
                                    request_id=resp.headers.get("x-request-id")
                                    or resp.headers.get("request-id"),
                                    retry_after_seconds=_retry_after(
                                        resp.headers.get("retry-after")
                                    ),
                                ),
                            }
                        data = resp.json()
                        msg_id = (data.get("messages") or [{}])[0].get("id", "unknown")
                        logger.info("WhatsApp template sent successfully: msg_id={}", msg_id)
                        return {
                            "status": "ok",
                            "message_id": msg_id,
                            "_connection_id": connection_id,
                            "_provider_message_id": msg_id,
                        }
                except Exception as exc:
                    logger.error("WhatsApp dispatch exception: {}", exc)
                    return {
                        "status": "error",
                        "error": "WhatsApp request failed",
                        "_diagnostic": exception_diagnostic(
                            exc,
                            source="provider",
                            category="provider_request_failed",
                            code="whatsapp_request_failed",
                            message="WhatsApp provider request failed",
                            retryable=True,
                        ),
                    }

            if name in ("classify_jev", "classify_lead"):
                transcript = _extract_transcript(getattr(self, "context", None), self.tracker)
                classifier_cfg = self._snapshot.get("classifier", {})
                jev_cfg = classifier_cfg.get("jev", {})
                questions = jev_cfg.get("questions")
                if not questions:
                    from voice_runtime.contracts.cadence import default_jev_questions

                    questions = {k: v.model_dump() for k, v in default_jev_questions().items()}
                elif isinstance(questions, dict):
                    questions = {
                        k: (v.model_dump() if hasattr(v, "model_dump") else v)
                        for k, v in questions.items()
                    }
                jev_key = getattr(self.settings, "jev_api_key", None) or os.getenv(
                    "VOICE_JEV_API_KEY", ""
                )
                res = await run_jev_classification(
                    api_key=jev_key,
                    transcript=transcript,
                    questions=questions,
                    model=jev_cfg.get("model", "jev-latest"),
                    api_url=jev_cfg.get("api_url", "https://api.typesafe.ai/v1/systemone"),
                )
                logger.info("JEV CLASSIFY RESULT: {}", res)
                trimmed = trim_classifier_result(res)
                if isinstance(res.get("_diagnostic"), dict):
                    trimmed["_diagnostic"] = res["_diagnostic"]
                return trimmed

            if name == "classify_llm":
                transcript = _extract_transcript(getattr(self, "context", None), self.tracker)
                classifier_cfg = self._snapshot.get("classifier", {})
                llm_cfg = classifier_cfg.get("model", {})
                groq_key = getattr(self.settings, "groq_api_key", None) or os.getenv(
                    "VOICE_GROQ_API_KEY", ""
                )
                res = await run_llm_classification(
                    api_key=groq_key,
                    transcript=transcript,
                    prompt=classifier_cfg.get(
                        "prompt", "Classify the supplied conversation using only observed evidence."
                    ),
                    model=llm_cfg.get("model", "llama-3.3-70b-versatile"),
                )
                logger.info("LLM CLASSIFY RESULT: {}", res)
                trimmed = trim_classifier_result(res)
                if isinstance(res.get("_diagnostic"), dict):
                    trimmed["_diagnostic"] = res["_diagnostic"]
                return trimmed

            if name in ("check_callback_availability", "book_callback"):
                endpoint = (
                    "http://localhost:8000/api/v1/callback-scheduling/availability"
                    if name == "check_callback_availability"
                    else "http://localhost:8000/api/v1/callback-scheduling/book"
                )
                contact = (
                    self._snapshot.get("_resolved", {}).get("contact")
                    or self._snapshot.get("contact_snapshot")
                    or {}
                )
                payload = {
                    "agent_version_id": self._snapshot.get("agent_version_id"),
                    "contact_id": contact.get("id") or self._snapshot.get("contact_id"),
                }
                if name == "check_callback_availability":
                    payload.update(
                        {"timeframe": args.get("timeframe", ""), "role": args.get("role", "")}
                    )
                    if args.get("duration_minutes") is not None:
                        payload["duration_minutes"] = args["duration_minutes"]
                else:
                    payload.update(
                        {
                            "slot_id": args.get("slot_id", ""),
                            "reason": args.get("reason", "Customer requested callback"),
                        }
                    )
                token = getattr(self.settings, "operator_token", None) or os.getenv(
                    "VOICE_OPERATOR_TOKEN", ""
                )
                try:
                    async with httpx.AsyncClient(timeout=20) as client:
                        response = await client.post(
                            endpoint, json=payload, headers={"Authorization": f"Bearer {token}"}
                        )
                    return response.json()
                except Exception as exc:
                    logger.error("human callback tool failed: {}", exc)
                    return {"status": "error", "error": "Callback scheduling service unavailable"}
            if name == "schedule_callback":
                raw_time = (
                    args.get("time")
                    or args.get("when")
                    or args.get("due_at")
                    or args.get("phrase")
                    or "tomorrow morning"
                )
                reason = args.get("reason") or "Customer requested callback"
                contact = (
                    self._snapshot.get("_resolved", {}).get("contact")
                    or self._snapshot.get("contact_snapshot")
                    or {}
                )
                contact_id = contact.get("id") or self._snapshot.get("contact_id")
                agent_version_id = self._snapshot.get("agent_version_id") or (
                    self._snapshot.get("_resolved", {}).get("agent_version") or {}
                ).get("id")
                if not contact_id or not agent_version_id:
                    logger.warning("schedule_callback missing contact_id or agent_version_id")
                    return {
                        "status": "error",
                        "error": "Contact ID or Agent Version ID not found in session",
                    }

                timezone = contact.get("timezone") or "Asia/Kolkata"
                due_at = _parse_spoken_callback_time(raw_time)

                try:
                    from uuid import uuid4

                    from voice_api.db.session import SessionFactory
                    from voice_api.models import Callback

                    request_key = f"{self.run_id}_{uuid4().hex[:8]}"
                    async with SessionFactory() as session:
                        cb = Callback(
                            request_key=request_key,
                            contact_id=contact_id,
                            agent_version_id=agent_version_id,
                            due_at=due_at,
                            timezone=timezone,
                            original_phrase=f"{raw_time} ({reason})",
                            status="scheduled",
                        )
                        session.add(cb)
                        await session.commit()
                        logger.info(
                            "SCHEDULE_CALLBACK created callback id={} due_at={}", cb.id, due_at
                        )
                        return {
                            "status": "ok",
                            "callback_id": cb.id,
                            "scheduled_time": due_at.strftime("%A at %I:%M %p UTC"),
                            "message": f"Callback confirmed for {due_at.strftime('%A at %I:%M %p')}",
                        }
                except Exception as exc:
                    logger.error("schedule_callback failed to persist: {}", exc)
                    return {"status": "error", "error": f"Failed to persist callback: {exc}"}

            if (
                name == "query_knowledge_base"
                or name.startswith("query_knowledge_base_")
                or name.startswith("query_kb_")
                or ("knowledge" in name and "query" in name)
            ):
                query_text = (
                    args.get("query")
                    or args.get("question")
                    or args.get("search")
                    or args.get("topic")
                    or ""
                ).strip()
                if not query_text:
                    return {"status": "error", "error": "Missing search query parameter"}

                kb_ids = []
                assigned_kbs = self._snapshot.get("_resolved", {}).get("knowledge") or []
                for k in assigned_kbs:
                    if k.get("id"):
                        kb_ids.append(k["id"])
                if not kb_ids and self._snapshot.get("knowledge_base_ids"):
                    kb_ids = list(self._snapshot["knowledge_base_ids"])

                if not kb_ids:
                    try:
                        from sqlalchemy import select
                        from voice_api.db.session import SessionFactory
                        from voice_api.models import KnowledgeBase

                        async with SessionFactory() as db_session:
                            all_rows = (await db_session.scalars(select(KnowledgeBase.id))).all()
                            kb_ids = list(all_rows)
                    except Exception as exc:
                        logger.warning("Failed to look up knowledge bases in DB: {}", exc)

                if not kb_ids:
                    return {
                        "status": "not_found",
                        "hits": [],
                        "context": "No knowledge bases are linked to this agent.",
                    }

                all_hits = []
                try:
                    from voice_api.db.session import SessionFactory
                    from voice_api.knowledge.embeddings import GeminiEmbedder
                    from voice_api.services.knowledge_service import search

                    from voice_runtime.contracts.knowledge import RetrievalConfig

                    gemini_key = getattr(self.settings, "gemini_api_key", None) or os.getenv(
                        "GEMINI_API_KEY", ""
                    )
                    retrieval_cfg = RetrievalConfig.model_validate(
                        self._snapshot.get("retrieval", {})
                    )

                    async with SessionFactory() as db_session, httpx.AsyncClient() as http_client:
                        embedder = GeminiEmbedder(gemini_key, http_client) if gemini_key else None
                        for kb_id in kb_ids:
                            hits = await search(db_session, kb_id, query_text, retrieval_cfg, embedder)
                            all_hits.extend(hits)
                except Exception as exc:
                    logger.error("RAG search failed for query '{}': {}", query_text, exc)
                    return {"status": "error", "error": f"Knowledge search failed: {exc}"}

                all_hits.sort(key=lambda h: h.score, reverse=True)
                top_hits = all_hits[:5]
                if not top_hits:
                    return {
                        "status": "not_found",
                        "hits": [],
                        "context": "No relevant information found in knowledge base.",
                    }

                context_excerpts = "\n\n".join(
                    f"[{h.title}]\n{h.content}" for h in top_hits[:3]
                )
                return {
                    "status": "ok",
                    "hits_count": len(top_hits),
                    "context": context_excerpts,
                    "results": [
                        {
                            "title": h.title,
                            "content": h.content,
                            "score": round(h.score, 4),
                        }
                        for h in top_hits
                    ],
                }

            return {"status": "error", "error": "Tool adapter is not connected to live runtime"}

        return handle

    async def prepare(self, snapshot: dict, tracker: ExchangeTracker, *, transport=None) -> None:
        self.tracker, self._snapshot = tracker, snapshot
        self._nodes = {node["id"]: node for node in snapshot["flow"]["nodes"]}
        if snapshot.get("background_hooks") or any(
            node.get("entry_actions") or node.get("exit_actions") for node in self._nodes.values()
        ):
            raise ValueError(
                "Background hooks and entry/exit actions are not supported by live runtime"
            )
        for binding_key, binding in snapshot["_resolved"]["tools"].items():
            definition = binding["definition"]
            if definition["kind"] != "registered":
                raise ValueError("HTTP tools are not supported by live runtime")
            if not is_registered_handler(definition.get("handler")):
                raise ValueError(
                    f"Tool binding '{binding_key}' uses an unregistered runtime handler"
                )
        for key in self._nodes:
            for name in self._nodes[key]["tool_bindings"]:
                if name not in snapshot["_resolved"]["tools"]:
                    raise ValueError("Node references unavailable tool binding")
        for name, value in (
            ("sarvam_api_key", self.settings.sarvam_api_key),
            ("groq_api_key", self.settings.groq_api_key),
        ):
            if not value:
                raise ValueError(f"{name} is not configured")
        if snapshot["tts"]["provider"] == "cartesia" and not self.settings.cartesia_api_key:
            raise ValueError("cartesia_api_key is not configured")
        rate = snapshot["audio"]["sample_rate"]
        self.directory.mkdir(parents=True, exist_ok=True)
        self.capture = CallCapture(self.directory, rate)
        if transport is None:
            # Legacy SIM7600 path: construct transport from endpoint config.
            endpoint = snapshot["_resolved"]["endpoint"]
            from voice_runtime.telephony.usb_audio import Sim7600UsbAudioBridge

            transport = Sim7600UsbAudioBridge(
                endpoint["audio_port"],
                endpoint["baudrate"],
                sample_rate=rate,
                channels=1,
                capture=self.capture,
                frame_ms=snapshot["audio"]["frame_ms"],
            ).transport()
        stt, tts = build_speech_services(self.settings, snapshot, rate)
        llm_config = snapshot["llm"]
        llm_settings = {
            "model": llm_config["model"],
            "system_instruction": snapshot["system_prompt"],
            "reasoning_effort": llm_config["reasoning_effort"],
            "temperature": llm_config["temperature"],
            "max_tokens": llm_config["max_tokens"],
        }
        if llm_config.get("top_p") is not None:
            llm_settings["top_p"] = llm_config["top_p"]
        if llm_config["provider"] == "groq":
            llm = GroqLLMService(
                api_key=self.settings.groq_api_key,
                settings=GroqLLMService.Settings(**llm_settings),
            )
        elif llm_config["provider"] == "gemini":
            if not self.settings.gemini_api_key:
                raise ValueError("Gemini API key is not configured")
            # Preserve provider-default thinking. No universal disable setting exists.
            llm = GoogleLLMService(
                api_key=self.settings.gemini_api_key,
                settings=GoogleLLMService.Settings(llm_settings),
            )
        else:
            raise ValueError("Unsupported LLM provider")
        tts_config = snapshot["tts"]
        vad_config = snapshot["vad"]
        vad = SileroVADAnalyzer(
            sample_rate=rate,
            params=VADParams(
                confidence=vad_config["confidence"],
                start_secs=vad_config["start_secs"],
                stop_secs=vad_config["stop_secs"],
                min_volume=vad_config["min_volume"],
            ),
        )
        contact = (
            snapshot.get("_resolved", {}).get("contact") or snapshot.get("contact_snapshot") or {}
        )
        temporal = resolve_local_time_context(contact.get("timezone"))
        allowed_vars = snapshot.get("contact_variables", [])
        sanitized_contact = sanitize_contact_variables(contact, allowed_vars)

        flow_state: dict[str, Any] = dict(temporal)
        flow_state["contact"] = sanitized_contact
        flow_state.update(sanitized_contact)
        for variable in allowed_vars:
            flow_state.setdefault(variable, "")

        configured_opening = snapshot.get("greeting") or ""
        self._verbatim_opening = (
            render_opening(configured_opening, flow_state)
            if configured_opening.strip()
            else None
        )
        initial_messages: list[dict[str, str]] = []
        if not self._verbatim_opening:
            kickoff_greeting = configured_opening
            if not kickoff_greeting:
                name_phrase = (
                    f" to {sanitized_contact['name']}" if "name" in sanitized_contact else ""
                )
                kickoff_greeting = (
                    f"Start the phone conversation with a friendly '{temporal['greeting_phrase']}'"
                    f"{name_phrase}. "
                    f"Caller's local time is {temporal['local_time_12h']} "
                    f"({temporal['local_time_24h']})."
                )
            initial_messages = [{"role": "user", "content": kickoff_greeting}]

        context = LLMContext(initial_messages)
        self.context = context
        aggregators = LLMContextAggregatorPair(
            context,
            user_params=LLMUserAggregatorParams(vad_analyzer=vad),
        )
        bind_transcripts(aggregators, tracker)
        pipeline = Pipeline(
            [
                transport.input(),
                stt,
                aggregators.user(),
                llm,
                tts,
                transport.output(),
                aggregators.assistant(),
            ]
        )
        self.observer = EvidenceObserver(
            tracker,
            llm=llm,
            stt=stt,
            tts=tts,
            llm_model=llm_config["model"],
            stt_model=snapshot["stt"]["model"],
            tts_model=tts_config["model"],
            log_path=self.directory / "pipeline.log"
            if snapshot["_resolved"]["pipeline_logs_enabled"]
            else None,
        )
        self.worker = PipelineWorker(
            pipeline,
            observers=[self.observer, self.capture],
            enable_rtvi=False,
            params=PipelineParams(
                enable_metrics=True,
                audio_in_sample_rate=rate,
                audio_out_sample_rate=rate,
            ),
        )
        self.flow = TracedFlowManager(
            worker=self.worker,
            llm=llm,
            context_aggregator=aggregators,
            transport=transport,
            tracker=tracker,
            bindings=snapshot["_resolved"]["tools"],
            observer=self.observer,
            context=context,
            classifier_runner=self._run_node_classifier,
        )
        self.flow.state.update(flow_state)

        @self.worker.event_handler("on_pipeline_started")
        async def started(_worker, _frame):
            self.ready.set()

        @self.worker.event_handler("on_pipeline_error")
        async def failed(_worker, frame):
            if not self._call_hung_up:
                err_msg = getattr(frame, "error", None) or "inspect evidence"
                logger.warning("Pipeline error during active call: {}", err_msg)
                self.errors.append(f"Pipeline failed: {err_msg}")
                if self.tracker is not None:
                    diagnostic = text_error_diagnostic(str(err_msg))
                    self.tracker.diagnostic(**diagnostic)
            await self.worker.cancel()

        runner = WorkerRunner(handle_sigint=False, handle_sigterm=False)
        await runner.add_workers(self.worker)
        self.runner_task = asyncio.create_task(runner.run(), name=f"pipeline-{self.run_id}")
        async with asyncio.timeout(15):
            await self.ready.wait()

    async def converse(self, modem_or_check=None) -> dict:
        """Run conversation until pipeline ends or call drops.

        modem_or_check can be:
          - A modem object with async .state() -> CallState  (SIM7600 path)
          - An async callable returning bool (True=still active) (Twilio/generic)
          - None (no liveness polling; pipeline ends on its own)
        """
        self.tracker.begin("greeting")
        await self.flow.initialize(self._node(self._snapshot["flow"]["initial_node"]))
        if self._verbatim_opening:
            await self.worker.queue_frame(
                TTSSpeakFrame(self._verbatim_opening, append_to_context=True)
            )

        async def _check_active() -> bool:
            if modem_or_check is None:
                return True
            if callable(modem_or_check) and not hasattr(modem_or_check, "state"):
                return await modem_or_check()
            # Legacy SIM modem path
            return await modem_or_check.state() == CallState.ACTIVE

        while self.runner_task and not self.runner_task.done():
            if self.errors and not self._call_hung_up:
                raise RuntimeError(self.errors[-1])
            await asyncio.sleep(1)
            if not await _check_active():
                await self._record_call_termination(modem_or_check)
                self._call_hung_up = True
                await self.worker.cancel()
                break
        if self.runner_task:
            await self.runner_task
        if self.errors and not self._call_hung_up:
            raise RuntimeError(self.errors[-1])
        return {"flow_node": self.flow.current_node}

    async def _record_call_termination(self, modem_or_check) -> None:
        if self._termination_diagnostic_recorded or self.tracker is None:
            return
        self._termination_diagnostic_recorded = True
        if modem_or_check is None:
            return
        if callable(modem_or_check) and not hasattr(modem_or_check, "state"):
            self.tracker.diagnostic(
                severity="warning",
                category="call_termination",
                source="transport",
                code="remote_hangup",
                message="Telephony transport reported that the call ended",
                uncertain=True,
            )
            return
        try:
            status = await modem_or_check.status()
        except Exception as exc:
            self.tracker.diagnostic(
                severity="error",
                category="modem_failure",
                source="modem",
                code="termination_status_unavailable",
                message="Could not read modem state at call termination",
                detail=str(exc),
                uncertain=True,
            )
            return
        metadata = {
            "alive": status.alive,
            "serial_connected": status.serial_connected,
            "sim_ready": status.sim_ready,
            "voice_registered": status.voice_registered,
            "call_state": status.call_state.value,
            "rssi": status.rssi,
            "signal_quality": status.signal_quality,
            "operator": status.operator,
            "radio_access": status.radio_access,
            "usb_audio_active": status.usb_audio_active,
        }
        if status.rssi is not None and status.rssi <= 5:
            self.tracker.diagnostic(
                severity="warning",
                category="modem_signal",
                source="modem",
                code="low_signal_observed",
                message="Low modem signal was observed near call termination",
                uncertain=True,
                metadata=metadata,
            )
        if not status.voice_registered:
            code, message, category = (
                "network_unregistered",
                "Modem was not voice-registered when the call ended",
                "modem_network",
            )
        elif not status.alive or not status.serial_connected:
            code, message, category = (
                "modem_disconnected",
                "Modem connection was unavailable when the call ended",
                "modem_failure",
            )
        elif status.last_error:
            code, message, category = (
                "modem_command_error",
                "Modem reported an error near call termination",
                "modem_failure",
            )
        else:
            code, message, category = (
                "remote_hangup",
                "The call ended without an agent hangup request",
                "call_termination",
            )
        self.tracker.diagnostic(
            severity="warning" if category == "call_termination" else "error",
            category=category,
            source="modem",
            code=code,
            message=message,
            detail=status.last_error,
            uncertain=category == "call_termination",
            metadata=metadata,
        )

    async def close(self) -> None:
        try:
            if self.worker:
                await self.worker.cancel()
            if self.runner_task:
                await self.runner_task
            if self._end_task:
                await self._end_task
        finally:
            if self.tracker:
                self.tracker.end_visit("completed")
                self.tracker.end_exchange("completed")
            if self.observer:
                self.observer.close()
            if self.capture:
                self.capture.close()
