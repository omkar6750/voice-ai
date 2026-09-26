"""DB-snapshot-driven Pipecat host for one SIM7600 call.

This deliberately does not import the protected standalone demo.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
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
from voice_runtime.execution.contact_context import sanitize_contact_variables
from voice_runtime.execution.exchange import ExchangeTracker, bind_transcripts
from voice_runtime.execution.observer import EvidenceObserver
from voice_runtime.execution.temporal import resolve_local_time_context
from voice_runtime.telephony.base import CallState
from voice_runtime.telephony.usb_audio import Sim7600UsbAudioBridge


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
        logger.warning("JEV API key not configured on runtime; using fallback")
        return {
            "lead_temperature": {
                "choice": "warm",
                "probabilities": {"hot": 0.2, "warm": 0.6, "cold": 0.2},
                "confidence": 0.5,
                "rationale": "Jev API key missing",
            },
            "service_fit": {"choice": "strong_fit", "confidence": 0.5},
            "tone": {"choice": "receptive", "confidence": 0.5},
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
            logger.error("JEV System One HTTP {}: {}", resp.status_code, resp.text[:300])
    except Exception as exc:
        logger.error("JEV System One API error: {}", exc)
    return {
        "lead_temperature": {
            "choice": "warm",
            "probabilities": {"hot": 0.2, "warm": 0.6, "cold": 0.2},
            "confidence": 0.5,
            "rationale": "Fallback classification",
        },
        "service_fit": {"choice": "strong_fit", "confidence": 0.5},
        "tone": {"choice": "receptive", "confidence": 0.5},
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
            "lead_temperature": "warm",
            "service_fit": "strong_fit",
            "tone": "receptive",
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
            logger.error("LLM classification HTTP {}: {}", resp.status_code, resp.text[:300])
    except Exception as exc:
        logger.error("LLM classification error: {}", exc)
    return {
        "lead_temperature": "warm",
        "service_fit": "strong_fit",
        "tone": "receptive",
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
        self, *, tracker: ExchangeTracker, bindings: dict, observer: EvidenceObserver, **kwargs
    ):
        super().__init__(**kwargs)
        self.tracker = tracker
        self.bindings = bindings
        self.observer = observer
        self._transition_tool_id: str | None = None

    async def _set_node(self, node_id: str, node_config: NodeConfig) -> None:
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
                if isinstance(result, dict):
                    result = dict(result)
                    connection_id = result.pop("_connection_id", None)
                    provider_message_id = result.pop("_provider_message_id", None)
                self.tracker.tool_result(invocation_id, result, is_final=is_final)
                if (
                    name == "change_node"
                    and is_final
                    and isinstance(result, dict)
                    and result.get("status") == "ok"
                ):
                    self._transition_tool_id = invocation_id
                await original_callback(result, properties=properties)
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
                if not final_sent:
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
        self._end_task: asyncio.Task | None = None
        self.tracker: ExchangeTracker | None = None
        self._nodes: dict[str, dict] = {}
        self._snapshot: dict = {}

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

    async def _whatsapp_runtime_config(self) -> tuple[str, str, str | None, str, str | None]:
        """Return token, phone number, matching DB connection, and API version."""
        access_token = getattr(self.settings, "whatsapp_access_token", None) or os.getenv(
            "VOICE_WHATSAPP_ACCESS_TOKEN", ""
        )
        phone_number_id = getattr(self.settings, "whatsapp_phone_number_id", None) or os.getenv(
            "VOICE_WHATSAPP_PHONE_NUMBER_ID", ""
        )
        connection_id = None
        api_version = "v21.0"
        header_media_id = None
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
                    rows = (
                        await session.scalars(
                            select(IntegrationConnection).where(
                                IntegrationConnection.provider == "whatsapp",
                                IntegrationConnection.enabled.is_(True),
                            )
                        )
                    ).all()
                    for row in rows:
                        if str(row.config.get("phone_number_id", "")) == str(phone_number_id):
                            connection_id = str(row.id)
                            api_version = str(row.config.get("api_version") or api_version)
                            latest_media = await session.scalar(
                                select(IntegrationMedia)
                                .where(IntegrationMedia.connection_id == row.id)
                                .order_by(IntegrationMedia.uploaded_at.desc())
                            )
                            header_media_id = (
                                latest_media.provider_media_id if latest_media else None
                            )
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
        return access_token, phone_number_id, connection_id, api_version, header_media_id

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
                ) = await self._whatsapp_runtime_config()
                if not access_token or not phone_number_id:
                    logger.warning(
                        "WhatsApp credentials not configured on runtime; failing tool cleanly"
                    )
                    return {
                        "status": "error",
                        "error": "WhatsApp credentials not configured on runtime",
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
                                "error": f"WhatsApp API {resp.status_code}: {resp.text[:200]}",
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
                    return {"status": "error", "error": f"WhatsApp request failed: {exc}"}

            if name.startswith("whatsapp_template_"):
                (
                    access_token,
                    phone_number_id,
                    connection_id,
                    api_version,
                    db_header_media_id,
                ) = await self._whatsapp_runtime_config()
                if not access_token or not phone_number_id:
                    logger.warning(
                        "WhatsApp credentials not configured on runtime; failing tool cleanly"
                    )
                    return {
                        "status": "error",
                        "error": "WhatsApp credentials not configured on runtime",
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
                if name.startswith("whatsapp_template_"):
                    template_name = args.get("template_name") or name.removeprefix(
                        "whatsapp_template_"
                    )
                else:
                    template_name = (
                        args.get("template_name")
                        or getattr(self.settings, "whatsapp_template_name", None)
                        or os.getenv("VOICE_WHATSAPP_TEMPLATE_NAME", "dialtone_followup")
                    )
                tool_definition = (
                    self._snapshot.get("_resolved", {})
                    .get("tools", {})
                    .get(name, {})
                    .get("definition", {})
                )
                configured_media_id = tool_definition.get("header_media_id")
                header_media_id = configured_media_id or (
                    getattr(self.settings, "whatsapp_header_media_id", None)
                    or os.getenv("VOICE_WHATSAPP_HEADER_MEDIA_ID", "")
                    or db_header_media_id
                )

                summary = f"Thank you for speaking with Northstar Software Studio, {caller_name}! We have prepared your custom development overview and pricing catalog."
                if name == "send_followup" and args.get("message"):
                    summary = args["message"]
                elif args.get("message"):
                    summary = args["message"]

                components = []
                if header_media_id:
                    components.append(
                        {
                            "type": "header",
                            "parameters": [{"type": "image", "image": {"id": header_media_id}}],
                        }
                    )
                if args.get("components"):
                    components.extend(args["components"])
                else:
                    body_params = [{"type": "text", "text": caller_name}]
                    if args.get("message") or not name.startswith("whatsapp_template_"):
                        body_params.append(
                            {"type": "text", "text": " ".join(summary.split())[:1024]}
                        )
                    for k in sorted(args.keys()):
                        if k.startswith("param_") and k != "param_1":
                            body_params.append({"type": "text", "text": str(args[k])[:1024]})
                    components.append({"type": "body", "parameters": body_params})

                template_lang = args.get("language") or "en"
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
                                "error": f"WhatsApp API {resp.status_code}: {resp.text[:200]}",
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
                    return {"status": "error", "error": f"WhatsApp request failed: {exc}"}

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
                return trim_classifier_result(res)

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
                return trim_classifier_result(res)

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

            return {"status": "error", "error": "Tool adapter is not connected to live runtime"}

        return handle

    async def prepare(self, snapshot: dict, tracker: ExchangeTracker) -> None:
        self.tracker, self._snapshot = tracker, snapshot
        self._nodes = {node["id"]: node for node in snapshot["flow"]["nodes"]}
        if snapshot.get("background_hooks") or any(
            node.get("entry_actions") or node.get("exit_actions") for node in self._nodes.values()
        ):
            raise ValueError(
                "Background hooks and entry/exit actions are not supported by live runtime"
            )
        if any(
            binding["definition"]["kind"] != "registered"
            for binding in snapshot["_resolved"]["tools"].values()
        ):
            raise ValueError("HTTP tools are not supported by live runtime")
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
        endpoint = snapshot["_resolved"]["endpoint"]
        self.directory.mkdir(parents=True, exist_ok=True)
        self.capture = CallCapture(self.directory, rate)
        transport = Sim7600UsbAudioBridge(
            endpoint["audio_port"],
            endpoint["baudrate"],
            sample_rate=rate,
            channels=1,
            capture=self.capture,
            frame_ms=snapshot["audio"]["frame_ms"],
        ).transport()
        stt = SarvamSTTService(
            api_key=self.settings.sarvam_api_key,
            settings=SarvamSTTService.Settings(model=snapshot["stt"]["model"]),
            sample_rate=rate,
        )
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
        if tts_config["provider"] == "sarvam":
            tts = SarvamTTSService(
                api_key=self.settings.sarvam_api_key,
                settings=SarvamTTSService.Settings(
                    model=tts_config["model"],
                    voice=tts_config["voice"],
                    language=tts_config["language"],
                    pace=tts_config["pace"],
                ),
                sample_rate=rate,
            )
        else:
            tts = CartesiaTTSService(
                api_key=self.settings.cartesia_api_key,
                settings=CartesiaTTSService.Settings(voice=tts_config["voice"]),
                sample_rate=rate,
                encoding="pcm_s16le",
                container="raw",
            )
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

        kickoff_greeting = snapshot.get("greeting")
        if not kickoff_greeting:
            name_phrase = f" to {sanitized_contact['name']}" if "name" in sanitized_contact else ""
            kickoff_greeting = (
                f"Start the phone conversation with a friendly '{temporal['greeting_phrase']}'{name_phrase}. "
                f"Caller's local time is {temporal['local_time_12h']} ({temporal['local_time_24h']})."
            )

        context = LLMContext(
            [
                {
                    "role": "user",
                    "content": kickoff_greeting,
                }
            ]
        )
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
            observers=[self.observer],
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
        )
        # Populate flow state with temporal context for dynamic prompts
        self.flow.state.update(temporal)
        # Populate flow state with selectively whitelisted contact variables
        self.flow.state["contact"] = sanitized_contact
        for variable, value in sanitized_contact.items():
            self.flow.state[variable] = value
        # Ensure any allowed variable that is missing on this contact safely defaults to ""
        for variable in allowed_vars:
            if variable not in self.flow.state:
                self.flow.state[variable] = ""

        @self.worker.event_handler("on_pipeline_started")
        async def started(_worker, _frame):
            self.ready.set()

        @self.worker.event_handler("on_pipeline_error")
        async def failed(_worker, frame):
            if not self._call_hung_up:
                err_msg = getattr(frame, "error", None) or "inspect evidence"
                logger.warning("Pipeline error during active call: {}", err_msg)
                self.errors.append(f"Pipeline failed: {err_msg}")
            await self.worker.cancel()

        runner = WorkerRunner(handle_sigint=False, handle_sigterm=False)
        await runner.add_workers(self.worker)
        self.runner_task = asyncio.create_task(runner.run(), name=f"pipeline-{self.run_id}")
        async with asyncio.timeout(15):
            await self.ready.wait()

    async def converse(self, modem) -> dict:
        self.tracker.begin("greeting")
        await self.flow.initialize(self._node(self._snapshot["flow"]["initial_node"]))
        while self.runner_task and not self.runner_task.done():
            if self.errors and not self._call_hung_up:
                raise RuntimeError(self.errors[-1])
            await asyncio.sleep(1)
            if await modem.state() != CallState.ACTIVE:
                self._call_hung_up = True
                await self.worker.cancel()
                break
        if self.runner_task:
            await self.runner_task
        if self.errors and not self._call_hung_up:
            raise RuntimeError(self.errors[-1])
        return {"flow_node": self.flow.current_node}

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
