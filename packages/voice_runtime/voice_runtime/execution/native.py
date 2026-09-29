"""DB-snapshot-driven Pipecat host for one voice call.

Transport-neutral: the caller injects a ready Pipecat BaseTransport.
This deliberately does not import the protected standalone demo.
"""

from __future__ import annotations

import asyncio
import math
import os
import re
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.flows import ContextStrategy, ContextStrategyConfig, FlowManager, NodeConfig
from pipecat.flows.types import FlowsFunctionSchema
from pipecat.frames.frames import EndFrame, TTSSpeakFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMAssistantAggregatorParams,
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.services.google.llm import GoogleLLMService
from pipecat.services.groq.llm import GroqLLMService
from pipecat.turns.user_start import TranscriptionUserTurnStartStrategy, VADUserTurnStartStrategy
from pipecat.turns.user_turn_strategies import UserTurnStrategies
from pipecat.utils.context.llm_context_summarization import (
    LLMAutoContextSummarizationConfig,
    LLMContextSummaryConfig,
)
from pipecat.workers.runner import WorkerRunner

from voice_runtime.call_capture import CallCapture
from voice_runtime.contracts import is_registered_handler, validate_node_actions
from voice_runtime.contracts.prompt_references import compile_tool_references
from voice_runtime.diagnostics import (
    exception_diagnostic,
    provider_error_diagnostic,
    text_error_diagnostic,
)
from voice_runtime.execution.callback_http import CallbackHTTPError, post_callback_json
from voice_runtime.execution.classifier import (
    normalize_classifier_result,
    run_selected_classifier,
)
from voice_runtime.execution.contact_context import sanitize_contact_variables
from voice_runtime.execution.exchange import ExchangeTracker, bind_transcripts
from voice_runtime.execution.flow_manager import TracedFlowManager as TracedFlowManager
from voice_runtime.execution.observer import EvidenceObserver
from voice_runtime.execution.speech import build_speech_services as build_speech_services
from voice_runtime.execution.temporal import resolve_local_time_context
from voice_runtime.execution.termination import CallTermination
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
                raise ValueError(f"Opening references unavailable variable '{match.group(1)}'")
            value = value[part]
        return "" if value is None else str(value)

    return _OPENING_PLACEHOLDER.sub(replace, text)


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
    """Apply saved call controls to Pipecat's actual user-turn detector."""
    limits = snapshot["call_limits"]
    strategies = None
    if not limits["interruptions_enabled"]:
        strategies = UserTurnStrategies(
            start=[
                VADUserTurnStartStrategy(enable_interruptions=False),
                TranscriptionUserTurnStartStrategy(enable_interruptions=False),
            ]
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




class NativePipelineHost:
    def __init__(
        self,
        run_id: str,
        recordings_dir: Path,
        settings,
        *,
        graceful_close_timeout_secs: float = 15,
        termination: CallTermination | None = None,
    ) -> None:
        if not math.isfinite(graceful_close_timeout_secs) or graceful_close_timeout_secs <= 0:
            raise ValueError("Graceful close timeout must be finite and positive")
        self._graceful_close_timeout_secs = graceful_close_timeout_secs
        self.run_id, self.directory, self.settings = run_id, recordings_dir / run_id, settings
        self.worker = self.flow = self.capture = self.observer = None
        self.runner_task: asyncio.Task | None = None
        self.ready = asyncio.Event()
        self.errors: list[str] = []
        self._call_hung_up: bool = False
        self._end_frame_queued = False
        self.termination = termination if termination is not None else CallTermination()
        self._termination_diagnostic_recorded = False
        self._end_task: asyncio.Task | None = None
        self._idle_reprompts = 0
        self.tracker: ExchangeTracker | None = None
        self._nodes: dict[str, dict] = {}
        self._snapshot: dict = {}
        self._verbatim_opening: str | None = None
        self._exchange_count = 0
        self._classifier_cadence_running = False
        self._close_lock = asyncio.Lock()
        self._close_attempted = False
        self._close_error: BaseException | None = None

    def _node(self, key: str) -> NodeConfig:
        """Adapt one saved graph node into Pipecat's native NodeConfig shape."""
        node = self._nodes[key]
        flow = self._snapshot["flow"]
        role_message = node.get("role_prompt")
        if key == flow.get("initial_node") and not role_message:
            role_message = self._snapshot.get("system_prompt", "")
        if "initial_node" not in flow and not role_message:
            # Compatibility for pre-Pipecat snapshots used by older evidence tests.
            role_message = node.get("prompt", "")
        transitions = node.get("transitions", [])
        node_bindings = [
            name for name in node["tool_bindings"] if name != "change_node" or transitions
        ]
        exposed_tools = set(node_bindings)
        role_message = compile_tool_references(role_message or "", exposed_tools)
        task_messages = []
        if node.get("prompt"):
            task_messages.append(
                {
                    "role": "user",
                    "content": compile_tool_references(node["prompt"], exposed_tools),
                }
            )
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
        for name in node_bindings:
            tool = bindings[name]["definition"]
            parameters = tool["parameters"]
            properties = deepcopy(parameters.get("properties", {}))
            if name == "change_node":
                node_property = properties.get("node")
                if isinstance(node_property, dict):
                    node_property["enum"] = list(transitions)
            functions.append(
                FlowsFunctionSchema(
                    name=name,
                    description=tool["description"],
                    properties=properties,
                    required=parameters.get("required", []),
                    handler=self._handler(name),
                )
            )
        config = NodeConfig(
            name=key,
            role_message=role_message or "",
            task_messages=task_messages,
            functions=functions,
            respond_immediately=node["respond_immediately"],
            context_strategy=ContextStrategyConfig(
                strategy=ContextStrategy(node.get("context_strategy", "append"))
            ),
        )
        if node.get("terminal"):
            # Pipecat serializes this control frame behind synthesis and local
            # output audio. It is not a claim of browser/carrier playback.
            config["post_actions"] = [
                {"type": "function", "handler": self._terminal_response_finished, "node": key}
            ]
        return config

    async def _terminal_response_finished(self, action: dict, manager: FlowManager) -> None:
        """Complete a terminal visit only when its ordered post-action reaches output."""
        node = action["node"]
        if manager.current_node != node or self.termination.closing:
            return
        self.termination.summary.terminal_node = node
        self.termination.request("terminal_completed", graceful=True)
        self._call_hung_up = True
        self.tracker.diagnostic(
            severity="info",
            category="call_termination",
            source="call",
            code="terminal_completed",
            message="Terminal node response reached local output completion",
            metadata={"node": node, "playback_scope": "local_output"},
        )
        try:
            await self._finish_end_call()
        except Exception:
            self.termination.request("pipeline_failure")
            self.errors.append("Terminal shutdown could not be queued")
            self.tracker.diagnostic(
                severity="error",
                category="call_termination",
                source="runtime",
                code="terminal_shutdown_failed",
                message="Terminal shutdown could not be queued",
            )
            raise

    async def _handle_user_idle(self) -> None:
        if self._call_hung_up or self.worker is None:
            return
        if self._idle_reprompts == 0:
            self._idle_reprompts = 1
            await self.worker.queue_frame(
                TTSSpeakFrame("Are you still there?", append_to_context=True)
            )
            return
        self._call_hung_up = True
        self.termination.request("caller_idle_timeout")
        if self.tracker is not None:
            self.tracker.diagnostic(
                severity="info",
                category="call_termination",
                source="call",
                code="caller_idle_timeout",
                message="Caller remained idle after one reprompt",
            )
        self._end_task = asyncio.create_task(self.worker.cancel())

    async def _run_node_classifier(
        self, phase: str, node_key: str, *, force: bool = False
    ) -> tuple[str, dict[str, str]] | None:
        """Run one configured node classifier and return its context message."""
        classifier_cfg = self._snapshot.get("classifier", {})
        if not classifier_cfg.get("enabled", True):
            return None
        configured_nodes = classifier_cfg.get(
            "node_entries" if phase == "entry" else "node_exits", []
        )
        if not force and node_key not in configured_nodes:
            return None
        if self.tracker is None:
            return None

        transcript = _extract_transcript(getattr(self, "context", None), self.tracker)
        classifier_type = classifier_cfg.get("classifier_type", "llm")
        selected = (
            classifier_cfg.get("jev") if classifier_type == "jev" else classifier_cfg.get("llm")
        )
        selected = selected or {}
        provider = "typesafe" if classifier_type == "jev" else selected.get("provider", "groq")
        model = selected.get(
            "model", "jev-latest" if classifier_type == "jev" else "qwen/qwen3.8-27b"
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

            async def jev_request(**kwargs):
                jev_cfg = kwargs["config"]
                questions = jev_cfg.get("questions") or {}
                if not questions:
                    from voice_runtime.contracts.cadence import default_jev_questions

                    questions = {
                        key: value.model_dump() for key, value in default_jev_questions().items()
                    }
                jev_key = getattr(self.settings, "jev_api_key", None) or os.getenv(
                    "VOICE_JEV_API_KEY", ""
                )
                return await run_jev_classification(
                    api_key=jev_key,
                    transcript=kwargs["transcript"],
                    questions=questions,
                    model=jev_cfg.get("model", "jev-latest"),
                    api_url=jev_cfg.get("api_url", "https://api.typesafe.ai/v1/systemone"),
                )

            raw_result = await run_selected_classifier(
                settings=self.settings,
                classifier=classifier_cfg,
                transcript=transcript,
                jev_request=jev_request,
            )
            result = normalize_classifier_result(
                raw_result,
                selected.get("output_fields"),
                max_result_chars=int(classifier_cfg.get("max_result_chars", 512)),
            )
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
        result_id, message = self.tracker.finish_classifier(operation, status, result, error=error)
        return result_id, message

    async def _run_classifier_cadence(self) -> None:
        """Run the configured classifier after every N finalized caller exchanges."""
        if self._classifier_cadence_running or not self.flow or not self.context:
            return
        config = self._snapshot.get("classifier", {})
        every_n = config.get("every_n_exchanges")
        if not config.get("enabled", True) or not every_n or self._exchange_count % every_n:
            return
        node_key = self.flow.current_node
        if not node_key:
            return
        self._classifier_cadence_running = True
        try:
            result = await self._run_node_classifier("entry", node_key, force=True)
            if result is not None:
                _, message = result
                # The user-turn event fires after Pipecat has pushed the current
                # context frame. This message is therefore deliberately made
                # available to the next LLM request, not retroactively injected
                # into the request already in flight.
                self.context.add_message(message)
        finally:
            self._classifier_cadence_running = False

    async def _whatsapp_runtime_config(
        self,
        *,
        connection_id: str | None = None,
    ) -> tuple[str, str, str | None, str]:
        """Resolve a pinned integration; template media IDs are already provider IDs."""
        access_token = getattr(self.settings, "whatsapp_access_token", None) or os.getenv(
            "VOICE_WHATSAPP_ACCESS_TOKEN", ""
        )
        phone_number_id = getattr(self.settings, "whatsapp_phone_number_id", None) or os.getenv(
            "VOICE_WHATSAPP_PHONE_NUMBER_ID", ""
        )
        if connection_id:
            # An explicitly pinned tool must fail closed instead of falling back
            # to unrelated process-wide WhatsApp credentials.
            access_token = ""
            phone_number_id = ""
        api_version = "v21.0"
        try:
            from sqlalchemy import select
            from voice_api.db.session import SessionFactory
            from voice_api.models import IntegrationConnection, IntegrationSecret
            from voice_api.services.vault_service import CredentialVault

            async with SessionFactory() as session:
                query = select(IntegrationConnection).where(
                    IntegrationConnection.provider == "whatsapp",
                    IntegrationConnection.enabled.is_(True),
                    IntegrationConnection.deleted_at.is_(None),
                )
                if connection_id:
                    query = query.where(IntegrationConnection.id == connection_id)
                elif phone_number_id:
                    query = query.where(
                        IntegrationConnection.config["phone_number_id"].astext == phone_number_id
                    )
                rows = (
                    await session.scalars(query.order_by(IntegrationConnection.created_at))
                ).all()
                row = rows[0] if rows else None
                if row is not None:
                    connection_id = str(row.id)
                    phone_number_id = str(row.config.get("phone_number_id") or "")
                    api_version = str(row.config.get("api_version") or api_version)
                    # A pinned template tool must use the secret belonging to that exact
                    # connection, never a process-wide token for another WhatsApp account.
                    secret = await session.scalar(
                        select(IntegrationSecret).where(
                            IntegrationSecret.connection_id == row.id,
                            IntegrationSecret.name == "access_token",
                        )
                    )
                    if secret is not None:
                        access_token = CredentialVault.from_env().decrypt(
                            secret.ciphertext, secret.key_id
                        )
        except Exception:
            logger.warning("Could not resolve configured WhatsApp integration")
        return (
            access_token,
            phone_number_id,
            connection_id,
            api_version,
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
                if self._call_hung_up:
                    return {"status": "ok"}
                self._call_hung_up = True
                self.termination.request("agent_hangup", graceful=True)
                self.tracker.diagnostic(
                    severity="info",
                    category="call_termination",
                    source="call",
                    code="agent_hangup",
                    message="Agent requested call termination",
                )
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
                (
                    access_token,
                    phone_number_id,
                    connection_id,
                    api_version,
                ) = await self._whatsapp_runtime_config(
                    connection_id=whatsapp_config.get("connection_id"),
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
                header = whatsapp_config.get("header")
                try:
                    payload = build_whatsapp_template_payload(
                        destination=recipient,
                        template_name=template_name,
                        language=str(whatsapp_config.get("language") or "en"),
                        header=header,
                        parameter_mappings=whatsapp_config.get("parameter_mappings") or {},
                        arguments=args,
                        caller_name=caller_name,
                    )
                except (TypeError, ValueError):
                    return {
                        "status": "error",
                        "error": "WhatsApp template configuration is invalid",
                        "_diagnostic": exception_diagnostic(
                            ValueError("invalid WhatsApp template configuration"),
                            source="runtime",
                            category="tool_configuration",
                            code="whatsapp_template_invalid",
                            message="WhatsApp template configuration is invalid",
                            retryable=False,
                        ),
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
                        result = {
                            "status": "ok",
                            "message_id": msg_id,
                            "_connection_id": connection_id,
                            "_provider_message_id": msg_id,
                        }
                        if isinstance(header, dict):
                            result["media_id"] = header["media_id"]
                        return result
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

            if name == "classify_lead":
                transcript = _extract_transcript(getattr(self, "context", None), self.tracker)
                classifier_cfg = self._snapshot.get("classifier", {})

                async def jev_request(**kwargs):
                    jev_cfg = kwargs["config"]
                    questions = jev_cfg.get("questions") or {}
                    if not questions:
                        from voice_runtime.contracts.cadence import default_jev_questions

                        questions = {k: v.model_dump() for k, v in default_jev_questions().items()}
                    jev_key = getattr(self.settings, "jev_api_key", None) or os.getenv(
                        "VOICE_JEV_API_KEY", ""
                    )
                    return await run_jev_classification(
                        api_key=jev_key,
                        transcript=kwargs["transcript"],
                        questions=questions,
                        model=jev_cfg.get("model", "jev-latest"),
                        api_url=jev_cfg.get("api_url", "https://api.typesafe.ai/v1/systemone"),
                    )

                result = await run_selected_classifier(
                    settings=self.settings,
                    classifier=classifier_cfg,
                    transcript=transcript,
                    jev_request=jev_request,
                )
                return normalize_classifier_result(
                    result,
                    (classifier_cfg.get("jev") or classifier_cfg.get("llm") or {}).get(
                        "output_fields"
                    ),
                    max_result_chars=int(classifier_cfg.get("max_result_chars", 512)),
                )

            if name in ("check_callback_availability", "book_callback"):
                api_base_url = (
                    getattr(self.settings, "api_base_url", None)
                    or os.getenv("VOICE_API_BASE_URL")
                    or "http://localhost:8000"
                ).rstrip("/")
                endpoint = (
                    f"{api_base_url}/api/v1/callback-scheduling/availability"
                    if name == "check_callback_availability"
                    else f"{api_base_url}/api/v1/callback-scheduling/book"
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
                        return await post_callback_json(client, endpoint, payload, token)
                except CallbackHTTPError as exc:
                    logger.warning("human callback tool received HTTP {}", exc.status_code)
                    return {
                        "status": "error",
                        "error": f"Callback scheduling service returned HTTP {exc.status_code}",
                    }
                except Exception as exc:
                    logger.error("human callback tool failed ({})", type(exc).__name__)
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

            definition = (
                self._snapshot.get("_resolved", {})
                .get("tools", {})
                .get(name, {})
                .get("definition", {})
            )
            if definition.get("handler") == "query_knowledge_base":
                query_text = (
                    args.get("query")
                    or args.get("question")
                    or args.get("search")
                    or args.get("topic")
                    or ""
                ).strip()
                if not query_text:
                    return {"status": "error", "error": "Missing search query parameter"}

                kb_id = definition.get("knowledge_base_id")
                attached_ids = {
                    kb["id"]
                    for kb in self._snapshot.get("_resolved", {}).get("knowledge", [])
                    if kb.get("id")
                }
                if not kb_id or kb_id not in attached_ids:
                    return {
                        "status": "error",
                        "error": "Knowledge tool is not scoped to an attached knowledge base",
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
                    f"[{h.title}; chunk {h.chunk_id}]\n{h.content[:600]}" for h in top_hits[:3]
                )
                return {
                    "status": "ok",
                    "knowledge_base_id": kb_id,
                    "hits_count": len(all_hits),
                    "context": context_excerpts,
                    "results": [
                        {
                            "chunk_id": h.chunk_id,
                            "title": h.title,
                            "source_path": h.source_path,
                            "score": round(h.score, 4),
                        }
                        for h in top_hits[:3]
                    ],
                }

            return {"status": "error", "error": "Tool adapter is not connected to live runtime"}

        return handle

    async def prepare(self, snapshot: dict, tracker: ExchangeTracker, *, transport=None) -> None:
        self.tracker, self._snapshot = tracker, snapshot
        self._nodes = {node["id"]: node for node in snapshot["flow"]["nodes"]}
        action_errors = validate_node_actions(
            snapshot,
            snapshot.get("_resolved", {}).get("tools", {}),
        )
        if action_errors:
            raise ValueError(action_errors[0])
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
        required_credentials = [("sarvam_api_key", self.settings.sarvam_api_key)]
        llm_provider = snapshot["llm"]["provider"]
        required_credentials.append(
            (
                "gemini_api_key" if llm_provider == "gemini" else "groq_api_key",
                self.settings.gemini_api_key
                if llm_provider == "gemini"
                else self.settings.groq_api_key,
            )
        )
        classifier_cfg = snapshot.get("classifier", {})
        if classifier_cfg.get("classifier_type") == "jev":
            required_credentials.append(
                ("jev_api_key", getattr(self.settings, "jev_api_key", None))
            )
        elif (classifier_cfg.get("llm") or {}).get("provider", "groq") == "gemini":
            required_credentials.append(("gemini_api_key", self.settings.gemini_api_key))
        else:
            required_credentials.append(("groq_api_key", self.settings.groq_api_key))
        summarizer_cfg = snapshot.get("context", {}).get("summarizer", {})
        if summarizer_cfg.get("enabled"):
            summary_provider = (summarizer_cfg.get("model") or {}).get("provider", llm_provider)
            required_credentials.append(
                (
                    "gemini_api_key" if summary_provider == "gemini" else "groq_api_key",
                    self.settings.gemini_api_key
                    if summary_provider == "gemini"
                    else self.settings.groq_api_key,
                )
            )
        for name, value in required_credentials:
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

        summarizer_cfg = snapshot.get("context", {}).get("summarizer", {})
        assistant_params = None
        if summarizer_cfg.get("enabled"):
            summary_model = summarizer_cfg.get("model") or {}
            summary_provider = summary_model.get("provider", llm_config["provider"])
            summary_settings = {
                "model": summary_model.get("model", llm_config["model"]),
                "temperature": summary_model.get("temperature", 0.4),
                "max_tokens": summary_model.get(
                    "max_tokens", summarizer_cfg.get("output_budget_tokens", 512)
                ),
            }
            if summary_model.get("top_p") is not None:
                summary_settings["top_p"] = summary_model["top_p"]
            if summary_provider == "groq":
                summary_llm = GroqLLMService(
                    api_key=self.settings.groq_api_key,
                    settings=GroqLLMService.Settings(
                        **summary_settings,
                        reasoning_effort="none",
                    ),
                )
            elif summary_provider == "gemini":
                summary_llm = GoogleLLMService(
                    api_key=self.settings.gemini_api_key,
                    settings=GoogleLLMService.Settings(**summary_settings),
                )
            else:
                raise ValueError(f"Unsupported summarizer provider: {summary_provider}")

            summary_config = LLMContextSummaryConfig(
                target_context_tokens=summarizer_cfg.get("output_budget_tokens", 512),
                min_messages_after_summary=summarizer_cfg.get("preserve_recent_messages", 6),
                summarization_prompt=summarizer_cfg.get("prompt"),
                llm=summary_llm,
            )
            assistant_params = LLMAssistantAggregatorParams(
                enable_auto_context_summarization=True,
                auto_context_summarization_config=LLMAutoContextSummarizationConfig(
                    max_context_tokens=summarizer_cfg.get("context_window_tokens", 8192),
                    # Pipecat measures messages; a normal caller/assistant
                    # exchange contributes two messages. Tool messages may
                    # cause an earlier safe compaction.
                    max_unsummarized_messages=max(
                        2, int(summarizer_cfg.get("every_n_exchanges", 10)) * 2
                    ),
                    summary_config=summary_config,
                ),
            )
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
            render_opening(configured_opening, flow_state) if configured_opening.strip() else None
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
            user_params=build_user_aggregator_params(snapshot, vad),
            assistant_params=assistant_params,
        )

        @aggregators.user().event_handler("on_user_turn_idle")
        async def on_user_turn_idle(_aggregator):
            await self._handle_user_idle()

        @aggregators.user().event_handler("on_user_turn_started")
        async def on_user_turn_started(_aggregator, strategy):
            self._idle_reprompts = 0
            self.observer.record_turn_event("user_turn_started", strategy=type(strategy).__name__)

        @aggregators.user().event_handler("on_user_turn_stopped")
        async def on_user_turn_stopped(_aggregator, strategy, _message):
            self.observer.record_turn_event("user_turn_stopped", strategy=type(strategy).__name__)

        @aggregators.user().event_handler("on_user_turn_inference_triggered")
        async def on_user_turn_inference_triggered(_aggregator, strategy):
            self.observer.record_turn_event(
                "user_turn_inference_triggered", strategy=type(strategy).__name__
            )

        @aggregators.user().event_handler("on_user_turn_message_added")
        async def on_user_turn_message_added(_aggregator, _message):
            self._exchange_count += 1
            await self._run_classifier_cadence()

        @aggregators.user().event_handler("on_user_turn_stop_timeout")
        async def on_user_turn_stop_timeout(_aggregator):
            self.observer.record_turn_event("user_turn_stop_timeout")

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
            llm_provider=llm_config["provider"],
            stt_provider=snapshot["stt"]["provider"],
            tts_provider=tts_config["provider"],
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
                enable_usage_metrics=True,
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
            snapshot=snapshot,
            observer=self.observer,
            context=context,
            classifier_runner=self._run_node_classifier,
            action_runner=self._run_node_action,
            end_call_runner=self._finish_end_call,
        )
        self.flow.state.update(flow_state)

        @self.worker.event_handler("on_pipeline_started")
        async def started(_worker, _frame):
            self.ready.set()

        @self.worker.event_handler("on_pipeline_error")
        async def failed(_worker, frame):
            await self._pipeline_failed(frame)

        runner = WorkerRunner(handle_sigint=False, handle_sigterm=False)
        await runner.add_workers(self.worker)
        self.runner_task = asyncio.create_task(runner.run(), name=f"pipeline-{self.run_id}")
        async with asyncio.timeout(15):
            await self.ready.wait()

    async def _run_node_action(self, phase: str, node_key: str, binding_key: str) -> bool:
        """Run one allow-listed action with no model supplied arguments."""
        binding = self.flow.bindings[binding_key]
        definition = binding["definition"]
        handler_name = definition["handler"]
        invocation_id = self.tracker.start_tool(
            binding_key,
            binding["version_id"],
            f"node-action-{uuid4().hex}",
            {},
            None,
        )
        tool_ended = False
        try:
            result = await self._handler(handler_name)({}, self.flow)
            if isinstance(result, tuple):
                result = result[0]
            result_failed = isinstance(result, dict) and result.get("status") == "error"
            self.tracker.tool_result(invocation_id, result, is_final=True)
            self.tracker.end_tool(
                invocation_id,
                "failed" if result_failed else "completed",
                result,
            )
            tool_ended = True
            if result_failed:
                raise RuntimeError(result.get("error", "Lifecycle action returned an error"))
            if (
                handler_name == "end_call"
                and isinstance(result, dict)
                and result.get("status") == "ok"
            ):
                await self._finish_end_call()
                return True
        except Exception as exc:
            if not tool_ended:
                self.tracker.end_tool(
                    invocation_id,
                    "failed",
                    {"error": f"{phase} action failed"},
                )
            self.tracker.diagnostic(
                severity="error",
                category="tool_failure",
                source="runtime",
                code="node_action_failed",
                message=f"Configured {phase} action failed for node '{node_key}'",
                metadata={"binding_key": binding_key, "error_type": type(exc).__name__},
            )
            raise
        return False

    async def _pipeline_failed(self, frame) -> None:
        """A shutdown request does not make a subsequent pipeline failure successful."""
        self.termination.request("pipeline_failure")
        err_msg = getattr(frame, "error", None) or "inspect evidence"
        logger.warning("Pipeline failed ({})", type(frame).__name__)
        self.errors.append(f"Pipeline failed: {err_msg}")
        if self.tracker is not None:
            self.tracker.diagnostic(**text_error_diagnostic(str(err_msg)))
        await self.worker.cancel()

    async def _finish_end_call(self) -> None:
        """Queue graceful shutdown once, after the final end-call tool result."""
        if self._end_frame_queued:
            return
        self._end_frame_queued = True
        try:
            await self.worker.queue_frame(EndFrame())
        except BaseException:
            self._end_frame_queued = False
            raise

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
            if self.errors:
                raise RuntimeError(self.errors[-1])
            if self.termination.graceful_deadline_expired(self._graceful_close_timeout_secs):
                self.termination.request("drain_timeout")
                self.tracker.diagnostic(
                    severity="error",
                    category="call_termination",
                    source="runtime",
                    code="graceful_close_timeout",
                    message="Graceful pipeline shutdown exceeded its deadline",
                    uncertain=True,
                    metadata={"timeout_seconds": self._graceful_close_timeout_secs},
                )
                await self.worker.cancel()
                raise TimeoutError("Graceful pipeline shutdown exceeded its deadline")
            await asyncio.sleep(1)
            if not await _check_active():
                await self._record_call_termination(modem_or_check)
                self._call_hung_up = True
                await self.worker.cancel()
                break
        if self.runner_task:
            await self.runner_task
        if self.errors:
            raise RuntimeError(self.errors[-1])
        self.termination.pipeline_finished()
        return {"flow_node": self.flow.current_node, "termination": self.termination.snapshot()}

    async def _record_call_termination(self, modem_or_check) -> None:
        # Liveness alone cannot distinguish a caller hangup from a network drop.
        self.termination.request("disconnect_unknown")
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
        async with self._close_lock:
            if self._close_error is not None:
                raise self._close_error
            if self._close_attempted:
                return

            primary_error: BaseException | None = None
            cleanup_error: BaseException | None = None

            try:
                if (
                    not self.termination.closing
                    and self.termination.summary.pipeline_finished_at_ns is None
                ):
                    self.termination.request("cancelled")
                elif self.runner_task and not self.runner_task.done():
                    self.termination.request("cancelled")
                if self.worker:
                    await self.worker.cancel()
                if self.runner_task:
                    await self.runner_task
                if self._end_task:
                    await self._end_task
            except asyncio.CancelledError as exc:
                self.termination.request("cancelled")
                primary_error = exc
            except Exception as exc:
                self.termination.request("pipeline_failure")
                primary_error = exc
            finally:
                def attempt_cleanup(action) -> None:
                    nonlocal cleanup_error
                    try:
                        action()
                    except BaseException as exc:
                        if cleanup_error is None:
                            cleanup_error = exc

                if self.tracker:
                    status = self.termination.summary.evidence_status
                    attempt_cleanup(lambda: self.tracker.end_visit(status))
                    attempt_cleanup(lambda: self.tracker.end_exchange(status))
                if self.observer:
                    attempt_cleanup(self.observer.close)
                if self.capture:
                    attempt_cleanup(self.capture.close)

            if cleanup_error is not None:
                self.termination.summary.cleanup_status = "uncertain"
            self._close_attempted = True
            self._close_error = primary_error or cleanup_error
            if self._close_error is not None:
                raise self._close_error
