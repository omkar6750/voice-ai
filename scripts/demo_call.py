"""SIM7600 Voice AI Demo: SDR Agent (Ava @ Northstar Software Studio).

Features:
- Automatic flow stage progression (Greeting -> Discovery -> Qualification -> Jev Decisions).
- Jev multi-choice classification engine for lead temperature & service fit.
- WhatsApp 24h window verification, direct composer messaging & follow-up template dispatch.
- Graceful callback scheduling, guardrails, abuse mitigation, and diplomatic exit handling.
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.flows import FlowManager, NodeConfig
from pipecat.flows.types import FlowsFunctionSchema
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.groq.llm import GroqLLMService
from pipecat.services.sarvam.stt import SarvamSTTService
from pipecat.services.sarvam.tts import SarvamTTSService
from pipecat.transports.base_transport import BaseTransport
from pipecat.workers.runner import WorkerRunner
from pydantic_settings import BaseSettings, SettingsConfigDict
from voice_runtime.call_capture import CallCapture
from voice_runtime.telephony.base import CallState
from voice_runtime.telephony.session import TelephonySession
from voice_runtime.telephony.sim7600 import Sim7600Modem
from voice_runtime.telephony.usb_audio import Sim7600UsbAudioBridge


class DemoProviderSettings(BaseSettings):
    cartesia_api_key: str = ""
    sarvam_api_key: str
    groq_api_key: str
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_template_name: str = "dialtone_followup"
    whatsapp_header_media_id: str = ""
    jev_api_key: str = ""

    model_config = SettingsConfigDict(env_prefix="VOICE_", env_file=".env", extra="ignore")


# ==============================================================================
# 1. HARDWARE & AUDIO CONFIGURATION
# ==============================================================================
AT_PORT = "COM16"
AUDIO_PORT = "COM17"
BAUDRATE = 115200

SAMPLE_RATE = 16000
CHANNELS = 1
FRAME_MS = 20
MAX_CALL_SECONDS = int(os.getenv("VOICE_MAX_CALL_SECONDS", "300"))
AT_COMMAND_TIMEOUT = 5.0

VAD_STOP_SECS = 0.8
VAD_START_SECS = 0.1
VAD_MIN_VOLUME = 0.1
VAD_CONFIDENCE = 0.5

# ==============================================================================
# 2. CRM LEAD DATA & SDR PERSONA (AVA @ NORTHSTAR)
# ==============================================================================
CRM_LEAD_DATA = {
    "rep_name": "Ava",
    "rep_role": "Senior Sales Development Representative",
    "company_offering": "Northstar Software Studio",
    "lead_source": "Instagram Ad (Scale Q3 Campaign)",
    "conversion_event": "Submitted contact details requesting custom software / app consultation",
    "service_inquired": "Custom Web & Mobile App Development (Pixel-Perfect UI, Motion Graphics, Scalable Cloud Backends)",
}

# Speech-to-Text & LLM
SARVAM_STT_MODEL = "saaras:v3"
GROQ_MODEL = "qwen/qwen3.8-27b"

# Active TTS Provider: "sarvam" or "cartesia"
ACTIVE_TTS_PROVIDER = "sarvam"

# Sarvam TTS Configuration (Bulbul v3 - Female Indian Voice - Multilingual: Hindi, Marathi, Telugu, English)
SARVAM_TTS_MODEL = "bulbul:v3"
SARVAM_TTS_VOICE = "ritu"  # Options: ritu, priya, kavya, neha, pooja, simran, amelia, sophia
SARVAM_TTS_LANGUAGE = "en-IN"

# Cartesia TTS Configuration (Preserved)
CARTESIA_VOICE_ID = "71a7ad14-091c-4e8e-a314-022ece01c121"

AGENT_TEMPERATURE = 0.4
AGENT_MAX_TOKENS = 180
AGENT_SYSTEM_INSTRUCTION = (
    f"You are {CRM_LEAD_DATA['rep_name']}, a professional and friendly {CRM_LEAD_DATA['rep_role']} at {CRM_LEAD_DATA['company_offering']}. "
    "You are conducting an outbound phone follow-up to a lead who clicked our ad requesting custom software consultation. "
    "Speak naturally like a sharp, genuine professional on a live phone call. Never mention that you are an AI. "
    "\n--- SPOKEN CONVERSATION RULES ---\n"
    "1. Keep turns concise: 1 to 2 spoken sentences per turn. Complete your sentences naturally without trailing off. "
    "2. Ask only ONE focused question at a time. "
    "3. Keep discovery questions open; provide examples only when the caller asks for clarification. "
    "4. Acknowledge the caller's points with a brief, punchy summary rather than repeating everything they said. "
    "5. Plain speech only: never use asterisks, markdown formatting, bullet points, or numbered lists. "
    "6. If the caller asks about project risk or guarantees (e.g., 'what if work is not done?'), reassure them that we work in weekly milestone sprints with regular demos and transparent sign-offs before each phase. "
    "\n--- MULTILINGUAL & CODE-MIXING RULES ---\n"
    "You are completely fluent in English, Hindi, Marathi, and Telugu, and naturally code-mix with English (Hinglish, Marathish, Tenglish) like a modern Indian tech professional. "
    "1. Language Locking: When the caller speaks in or requests Marathi, Hindi, or Telugu, IMMEDIATELY switch to that language and STAY in that language consistently for the rest of the conversation. Never spontaneously switch back to English unless the caller speaks in English. "
    "2. Do not use English meta-commentary like 'I will now speak in Marathi'—simply reply directly in the requested language. "
    "3. Script formatting: When replying in Hindi or Marathi, write native words in Devanagari script. When replying in Telugu, write native words in Telugu script (తెలుగు). Keep standard technical and business terms in English Latin script (e.g., 'custom software', 'web app', 'mobile app', 'MVP sprint', 'WhatsApp', 'pricing', 'cloud backend'). "
    "\n--- FLOW & TOOL RULES ---\n"
    "Use change_node to guide the call forward through each stage: "
    "- In greeting, when they agree to talk -> change_node(node='discovery') "
    "- In discovery, once they share what they are building -> change_node(node='qualification') "
    "- In qualification, understand their platform and broad use case, then transition to pricing -> change_node(node='hot_pricing') "
    "- In hot_pricing, state our MVP sprint pricing, offer the catalog, and call send_whatsapp_template(caller_name=...) "
    "- When concluding, or if the caller asks to hang up -> immediately call end_call()."
)

# ==============================================================================
# 3. WHATSAPP & COMPOSER CONFIGURATIONS
# ==============================================================================
WHATSAPP_GRAPH_API = "https://graph.facebook.com/v22.0"

COMPOSER_MODEL = "qwen/qwen3.8-27b"
COMPOSER_TEMPERATURE = 0.3
COMPOSER_MAX_TOKENS = 256

# Follow-up Template Composer Prompt (for pre-approved WhatsApp template dialtone_followup param {{2}})
TEMPLATE_COMPOSER_PROMPT = (
    "You compose follow-up summaries sent directly to the caller on WhatsApp. "
    "Write in the second person (address the caller as 'you'). "
    "Write 2-3 concise, friendly sentences summarizing what was discussed and any next steps. "
    "If you mention the caller's name, preserve the exact spelling provided. "
    "Plain text only, no markdown, no asterisks, no bullet points. "
    "Return only the summary text and nothing else."
)

# Direct Message Composer Prompt (for freeform WhatsApp text messages when 24h window is open)
DIRECT_MESSAGE_COMPOSER_PROMPT = (
    "You compose direct WhatsApp messages sent from the agent to the caller. "
    "You will receive the conversation transcript, any past WhatsApp messages, and specific instructions from the agent. "
    "Write a friendly, professional, and clear WhatsApp message in the second person addressing the caller directly. "
    "Plain text only, no asterisks, no markdown formatting. "
    "Return only the exact message body to be sent."
)

# ==============================================================================
# 4. CLASSIFIER CONFIGURATIONS (TYPESAFE AI JEV SYSTEM ONE & GROQ LLM)
# ==============================================================================
JEV_API_URL = "https://api.typesafe.ai/v1/systemone"
JEV_MODEL = "jev-latest"

LLM_CLASSIFIER_MODEL = "qwen/qwen3.8-27b"
LLM_CLASSIFIER_TEMPERATURE = 0.1

JEV_QUESTIONS = {
    "lead_temperature": {
        "type": "choice",
        "instructions": (
            "Classify the contact's current sales intent based primarily on their behavior and meaning in the conversation. "
            "Voice-call responses are often very short, so do not treat short answers such as 'yeah', 'okay', 'hmm', or 'sure' as negative by themselves. "
            "Consider whether the contact has a real need, demonstrates interest in the offering, asks buying-related questions, indicates timing or urgency, or shows resistance. "
            "When evidence supports multiple classifications or contains conflicting signals, preserve that uncertainty."
        ),
        "criteria": {
            "hot": "The contact shows clear current buying intent or meaningful progression toward a purchase. Signals may include confirming a real need, wanting the service soon, asking about price, timeline, implementation, next steps, availability, payment, or requesting a meeting or proposal. Short responses can still represent a hot lead when their meaning demonstrates intent.",
            "warm": "The contact shows genuine interest or relevance but has not demonstrated strong immediate purchase intent. They may listen, answer discovery questions positively, acknowledge a need, or ask general questions, but timing, commitment, urgency, or next-step intent remains uncertain.",
            "cold": "The contact demonstrates little current interest or weak relevance. Signals include saying they are only browsing, having no current need, rejecting the offering, repeatedly avoiding engagement, stating bad timing without future intent, or otherwise showing no meaningful movement toward a purchase.",
        },
    },
    "service_fit": {
        "type": "choice",
        "instructions": "Determine how closely the contact's actual need matches the service currently being offered (custom modern web & mobile app development).",
        "criteria": {
            "strong_fit": "The contact clearly needs custom web or mobile application development, UI/UX redesign, or secure cloud backends.",
            "possible_fit": "The need may overlap with the offered service (e.g. existing tech team needing support, adjacent integrations) but requires clarification.",
            "poor_fit": "The contact needs something materially different (e.g. non-software hardware, marketing-only, or no development needed).",
        },
    },
    "tone": {
        "type": "choice",
        "instructions": "What is the contact's conversational tone and attitude?",
        "criteria": {
            "receptive": "Friendly, engaged, curious, or actively answering questions.",
            "hesitant": "Reserved, busy, distracted, but not hostile.",
            "resistant": "Disinterested, irritated, abusive, or explicitly asking to stop.",
        },
    },
}

# ==============================================================================
# 5. FLOW NODE PROMPTS (AUTONOMOUS SDR FLOW)
# ==============================================================================
NODE_PROMPTS = {
    "greeting": (
        f"You are {CRM_LEAD_DATA['rep_name']} from {CRM_LEAD_DATA['company_offering']}. "
        "Warmly greet the caller, introduce yourself, and mention you are following up on their interest in custom software development. "
        "Ask if they have two quick minutes to chat right now. "
        "When they agree to talk, call change_node(node='discovery'). "
        "If they are busy, call change_node(node='callback_scheduling'). "
        "If they are not interested, call change_node(node='diplomatic_exit')."
    ),
    "discovery": (
        "You are in the discovery stage. Ask for their name if not yet known, and ask what kind of project or application they are looking to build. "
        "Keep your question open and simple without listing options. "
        "Once they share their initial idea, acknowledge it warmly and call change_node(node='qualification')."
    ),
    "qualification": (
        "You are in the qualification stage. Keep the caller engaged by asking one question at a time to understand two key things: "
        "1. The platform (web, mobile, or cross-platform, if not yet specified). "
        "2. Their broad use case or core workflow for the initial version. "
        "Acknowledge their answers with brief, natural validation. "
        "Once you have a clear picture of their platform and broad use case (or if they ask about pricing/timeline/next steps), call change_node(node='hot_pricing')."
    ),
    "hot_pricing": (
        "You are in the pricing and next-steps stage. "
        "State that our MVP Sprint packages range from $8k to $15k ready in 3-4 weeks with a 15% discount this quarter. "
        "IMMEDIATELY offer to send our full portfolio and pricing catalog to their WhatsApp right now, and CALL send_whatsapp_template(caller_name=...) to send it. "
        "Say: 'I just sent our catalog and pricing to your WhatsApp right now!' and ask if a quick 15-minute scoping call with our lead architect works for them. "
        "Once they confirm, call change_node(node='closing')."
    ),
    "warm_nurture": (
        "You are in the nurture stage. "
        "Reassure them that we build custom software tailored to their pace. "
        "Offer to send our portfolio to their WhatsApp (call send_whatsapp_template) and schedule a 15-minute chat with our tech team. "
        "Then call change_node(node='closing')."
    ),
    "diplomatic_exit": (
        "You are in the polite exit stage. "
        "Thank them for their time, offer to send our catalog to their WhatsApp just in case, and call end_call()."
    ),
    "callback_scheduling": (
        "Ask what day and time works best for a quick callback. "
        "Once they provide a time, confirm it warmly and call end_call()."
    ),
    "closing": (
        "Let them know the WhatsApp message is on its way. "
        "Thank them warmly, say goodbye, and call end_call()."
    ),
}

VALID_NODES = (
    "greeting",
    "discovery",
    "qualification",
    "hot_pricing",
    "warm_nurture",
    "diplomatic_exit",
    "callback_scheduling",
    "closing",
)


# ==============================================================================
# 6. TRANSCRIPT EXTRACTION & DIRECT JEV CLASSIFICATION ENGINE
# ==============================================================================


def _extract_transcript(context: LLMContext, limit: int = 25) -> str:
    """Extract clean dialogue exchanges from the LLM context."""
    transcript_lines = []
    for msg in context.messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role in ("user", "assistant") and content:
            label = "Caller" if role == "user" else "Agent"
            transcript_lines.append(f"{label}: {content}")
    return "\n".join(transcript_lines[-limit:])


async def run_jev_classification(
    settings: DemoProviderSettings,
    transcript: str,
) -> dict[str, Any]:
    """Execute official TypeSafe AI Jev System One multi-choice classification."""
    jev_payload = {
        "model": JEV_MODEL,
        "state": transcript,
        "questions": JEV_QUESTIONS,
    }

    if not settings.jev_api_key:
        logger.warning("JEV API key not configured")
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
                JEV_API_URL,
                json=jev_payload,
                headers={
                    "Authorization": f"Bearer {settings.jev_api_key}",
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
    settings: DemoProviderSettings,
    transcript: str,
) -> dict[str, Any]:
    """Execute Groq LLM multi-choice categorization."""
    llm_payload = {
        "state": transcript,
        "questions": JEV_QUESTIONS,
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                json={
                    "model": LLM_CLASSIFIER_MODEL,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are a multi-choice classification engine. "
                                "Evaluate the given dialogue state according to the provided questions and criteria. "
                                "Return your evaluation strictly as a valid JSON object matching the question keys."
                            ),
                        },
                        {"role": "user", "content": json.dumps(llm_payload, indent=2)},
                    ],
                    "temperature": LLM_CLASSIFIER_TEMPERATURE,
                    "response_format": {"type": "json_object"},
                },
                headers={"Authorization": f"Bearer {settings.groq_api_key}"},
            )
        if resp.status_code == 200:
            raw_data = json.loads(resp.json()["choices"][0]["message"]["content"])
            normalized: dict[str, Any] = {}
            for key, val in raw_data.items():
                if isinstance(val, str):
                    normalized[key] = {"choice": val, "confidence": 0.95}
                elif isinstance(val, dict):
                    normalized[key] = val
                else:
                    normalized[key] = {"choice": str(val), "confidence": 0.5}
            return normalized
        logger.error("LLM classification HTTP {}: {}", resp.status_code, resp.text[:300])
    except Exception as exc:
        logger.error("LLM classification error: {}", exc)

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


# ==============================================================================
# 7. TOOL FACTORY & FLOW HANDLERS
# ==============================================================================


async def change_node(
    args: dict,
    flow_manager: FlowManager | None = None,
) -> tuple[dict, NodeConfig | None]:
    """Move conversation to requested demo node (top-level compatibility function)."""
    node = args.get("node")
    if not isinstance(node, str) or node not in VALID_NODES:
        return {"error": f"node must be one of {VALID_NODES}"}, None
    current = flow_manager.current_node if flow_manager else "unknown"
    logger.info("FLOW transition {} -> {}", current, node)
    return {"status": "success", "node": node}, build_node(node)


def _make_tools(
    settings: DemoProviderSettings,
    context: LLMContext,
    number: str,
    worker: PipelineWorker | None = None,
    sales_state: dict[str, Any] | None = None,
) -> list[FlowsFunctionSchema]:
    """Build all interactive tools with closed-over state and dependencies."""
    if sales_state is None:
        sales_state = {}

    wa_number = "".join(c for c in number if c.isdigit())
    _bg_tasks: set[asyncio.Task[Any]] = set()
    tools_list: list[FlowsFunctionSchema] = []

    PRUNABLE_NODES = {"greeting"}

    def trim_classifier_result(res: dict) -> dict:
        """Schema-agnostic trimmer for classification output (Jev System One or LLM).
        Extracts clean key-value summaries of choices and top probabilities without verbose schemas.
        """
        if not isinstance(res, dict):
            return {"result": str(res)}
        trimmed = {}
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

    def prune_context_messages(
        messages: list[dict],
        target_node: str,
        prunable_nodes: set[str] = PRUNABLE_NODES,
    ) -> list[dict]:
        """Clean up context messages:
        1. Strip old 'change_node' assistant tool_calls and tool results.
        2. Strip old system task messages (since role_message replaces the system instruction).
        3. If target_node is beyond prunable nodes (e.g. entering qualification, hot_pricing, etc.),
           prune the initial greeting exchange while keeping discovery onwards.
        """
        cleaned = []
        change_node_ids = set()

        for m in messages:
            if m.get("role") == "assistant" and m.get("tool_calls"):
                for tc in m["tool_calls"]:
                    func = tc.get("function", {})
                    if func.get("name") == "change_node":
                        change_node_ids.add(tc.get("id"))

        for m in messages:
            role = m.get("role")
            if role == "system":
                continue
            if role == "tool" and m.get("tool_call_id") in change_node_ids:
                continue
            if role == "assistant" and m.get("tool_calls"):
                remaining_tcs = [
                    tc for tc in m["tool_calls"] if tc.get("id") not in change_node_ids
                ]
                if not remaining_tcs and not m.get("content"):
                    continue
                if not remaining_tcs and m.get("content"):
                    cleaned.append({"role": "assistant", "content": m["content"]})
                    continue
                cleaned.append({**m, "tool_calls": remaining_tcs})
                continue
            cleaned.append(m)

        if target_node not in ("greeting", "discovery") and "greeting" in prunable_nodes:
            final_list = []
            skip_greeting = True
            for m in cleaned:
                content = m.get("content") or ""
                if skip_greeting and (
                    "Start the phone conversation" in content
                    or "This is Ava calling" in content
                    or "two quick minutes" in content
                    or content.strip()
                    in ("Oh yeah sure", "Sure", "Yes", "Yeah", "Great, thanks for taking the time!")
                ):
                    continue
                skip_greeting = False
                final_list.append(m)
            return final_list

        return cleaned

    # --------------------------------------------------------------------------
    # Tool: tool/change-node
    # --------------------------------------------------------------------------
    async def handle_change_node(
        args: dict,
        flow_manager: FlowManager,
    ) -> tuple[dict, NodeConfig | None]:
        node = args.get("node")
        if not isinstance(node, str) or node not in VALID_NODES:
            return {"error": f"node must be one of {VALID_NODES}"}, None
        logger.info("FLOW transition {} -> {}", flow_manager.current_node, node)

        # Trigger Jev classification checkpoint out-of-band for CRM/metrics
        if flow_manager.current_node in ("discovery", "qualification"):
            transcript = _extract_transcript(context)

            async def _bg_classify():
                res = await run_jev_classification(settings, transcript)
                sales_state["jev_classification"] = res
                temp = res.get("lead_temperature", {})
                logger.info(
                    "JEV CHECKPOINT: temp={} (hot={:.2f}, warm={:.2f}, cold={:.2f}) fit={} tone={} conf={:.2f}",
                    temp.get("choice"),
                    temp.get("probabilities", {}).get("hot", 0.0),
                    temp.get("probabilities", {}).get("warm", 0.0),
                    temp.get("probabilities", {}).get("cold", 0.0),
                    res.get("service_fit", {}).get("choice"),
                    res.get("tone", {}).get("choice"),
                    temp.get("confidence", 0.0),
                )

            t = asyncio.create_task(_bg_classify())
            _bg_tasks.add(t)
            t.add_done_callback(_bg_tasks.discard)

        # Prune context messages to keep token usage low
        context.set_messages(prune_context_messages(context.get_messages(), target_node=node))

        return {}, build_node(node, tools_list)

    # --------------------------------------------------------------------------
    # Tool: tool/classify-jev (TypeSafe AI Jev System One)
    # --------------------------------------------------------------------------
    async def handle_classify_jev(
        _args: dict,
        _flow_manager: FlowManager,
    ) -> tuple[dict, NodeConfig | None]:
        """Execute TypeSafe AI Jev System One multi-choice classification."""
        transcript = _extract_transcript(context)
        res = await run_jev_classification(settings, transcript)
        sales_state["jev_classification"] = res
        temp = res.get("lead_temperature", {})
        logger.info(
            "JEV CLASSIFY TOOL: temp={} (hot={:.2f}, warm={:.2f}, cold={:.2f}) fit={} tone={} conf={:.2f}",
            temp.get("choice"),
            temp.get("probabilities", {}).get("hot", 0.0),
            temp.get("probabilities", {}).get("warm", 0.0),
            temp.get("probabilities", {}).get("cold", 0.0),
            res.get("service_fit", {}).get("choice"),
            res.get("tone", {}).get("choice"),
            temp.get("confidence", 0.0),
        )
        return res, None

    # --------------------------------------------------------------------------
    # Tool: tool/classify-llm (Groq LLM Classifier)
    # --------------------------------------------------------------------------
    async def handle_classify_llm(
        _args: dict,
        _flow_manager: FlowManager,
    ) -> tuple[dict, NodeConfig | None]:
        """Execute Groq LLM multi-choice categorization."""
        transcript = _extract_transcript(context)
        res = await run_llm_classification(settings, transcript)
        sales_state["llm_classification"] = res
        temp = res.get("lead_temperature", {})
        logger.info(
            "LLM CLASSIFY TOOL: temp={} fit={} tone={} conf={:.2f}",
            temp.get("choice"),
            res.get("service_fit", {}).get("choice"),
            res.get("tone", {}).get("choice"),
            temp.get("confidence", 0.0),
        )
        return trim_classifier_result(res), None

    # --------------------------------------------------------------------------
    # Tool: tool/end-call
    # --------------------------------------------------------------------------
    async def handle_end_call(
        _args: dict,
        _flow_manager: FlowManager,
    ) -> tuple[dict, NodeConfig | None]:
        logger.info("CALL end requested by agent/flow")
        if worker is not None:
            t = asyncio.create_task(worker.cancel())
            _bg_tasks.add(t)
            t.add_done_callback(_bg_tasks.discard)
        return {"status": "call_ended"}, None

    # --------------------------------------------------------------------------
    # Tool: tool/check-whatsapp-window
    # --------------------------------------------------------------------------
    async def handle_check_whatsapp_window(
        _args: dict,
        _flow_manager: FlowManager,
    ) -> tuple[dict, NodeConfig | None]:
        """Check if 24-hour customer service window is open."""
        window_open = sales_state.get("whatsapp_window_open", False)
        logger.info("WHATSAPP checking 24h window for {}: open={}", wa_number, window_open)
        if window_open:
            return {
                "window_open": True,
                "allowed_message_types": ["text", "template"],
                "recommendation": "24h window is open. Use send_whatsapp_message or send_whatsapp_template immediately. Do not discuss technical windows with the caller.",
            }, None
        return {
            "window_open": False,
            "allowed_message_types": ["template"],
            "recommendation": "24h window is closed. Immediately call send_whatsapp_template to deliver the follow-up without explaining Meta policies to the caller.",
        }, None

    # --------------------------------------------------------------------------
    # Tool: tool/send-whatsapp-message (Direct Composer Message)
    # --------------------------------------------------------------------------
    async def handle_send_whatsapp_message(
        args: dict,
        _flow_manager: FlowManager,
    ) -> tuple[dict, NodeConfig | None]:
        agent_instruction = args.get("agent_instruction", "")
        caller_name = args.get("caller_name", sales_state.get("caller_name", "there"))

        if not settings.whatsapp_access_token or not settings.whatsapp_phone_number_id:
            logger.error("WHATSAPP missing credentials")
            return {"status": "failed", "error": "WhatsApp not configured"}, None

        transcript = _extract_transcript(context)
        prompt_user_content = (
            f"Caller name: {caller_name}\n\n"
            f"Agent Instructions: {agent_instruction}\n\n"
            f"Phone Call Transcript:\n{transcript}"
        )

        logger.info("WHATSAPP composing direct message for {}", caller_name)
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    json={
                        "model": COMPOSER_MODEL,
                        "messages": [
                            {"role": "system", "content": DIRECT_MESSAGE_COMPOSER_PROMPT},
                            {"role": "user", "content": prompt_user_content},
                        ],
                        "temperature": COMPOSER_TEMPERATURE,
                        "max_tokens": COMPOSER_MAX_TOKENS,
                    },
                    headers={"Authorization": f"Bearer {settings.groq_api_key}"},
                )
            if resp.status_code >= 400:
                logger.error("WHATSAPP composer error: {} {}", resp.status_code, resp.text[:200])
                return {"status": "failed", "error": f"composer returned {resp.status_code}"}, None
            message_body = resp.json()["choices"][0]["message"]["content"].strip()
            logger.info("WHATSAPP direct message composed: {}", message_body[:120])
        except Exception as exc:
            logger.error("WHATSAPP composer failed: {}", exc)
            return {"status": "failed", "error": str(exc)}, None

        payload = {
            "messaging_product": "whatsapp",
            "to": wa_number,
            "type": "text",
            "text": {"body": message_body},
        }

        logger.info("WHATSAPP sending direct text to {}", wa_number)
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{WHATSAPP_GRAPH_API}/{settings.whatsapp_phone_number_id}/messages",
                    json=payload,
                    headers={"Authorization": f"Bearer {settings.whatsapp_access_token}"},
                )
            if resp.status_code >= 400:
                detail = resp.text[:300]
                logger.error("WHATSAPP direct send failed: {} {}", resp.status_code, detail)
                return {"status": "failed", "error": f"WhatsApp {resp.status_code}: {detail}"}, None
            msg_id = (resp.json().get("messages") or [{}])[0].get("id", "unknown")
            logger.info("WHATSAPP direct message sent message_id={}", msg_id)
            return {
                "sent": True,
                "type": "direct_message",
            }, None
        except Exception as exc:
            logger.error("WHATSAPP send failed: {}", exc)
            return {"sent": False, "error": str(exc)}, None

    # --------------------------------------------------------------------------
    # Tool: tool/send-whatsapp-template (Follow-up Template)
    # --------------------------------------------------------------------------
    async def handle_send_whatsapp_template(
        args: dict,
        _flow_manager: FlowManager,
    ) -> tuple[dict, NodeConfig | None]:
        caller_name = args.get("caller_name", "there")
        if not caller_name or not caller_name.strip():
            caller_name = "there"
        caller_name = caller_name.strip()
        sales_state["caller_name"] = caller_name

        if not settings.whatsapp_access_token or not settings.whatsapp_phone_number_id:
            logger.error("WHATSAPP missing credentials")
            return {"status": "failed", "error": "WhatsApp not configured"}, None

        transcript = _extract_transcript(context)
        logger.info("WHATSAPP composing template summary for {}", caller_name)
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    json={
                        "model": COMPOSER_MODEL,
                        "messages": [
                            {"role": "system", "content": TEMPLATE_COMPOSER_PROMPT},
                            {
                                "role": "user",
                                "content": f"Caller name: {caller_name}\n\nTranscript:\n{transcript}",
                            },
                        ],
                        "temperature": COMPOSER_TEMPERATURE,
                        "max_tokens": COMPOSER_MAX_TOKENS,
                    },
                    headers={"Authorization": f"Bearer {settings.groq_api_key}"},
                )
            if resp.status_code >= 400:
                logger.error("WHATSAPP composer error: {} {}", resp.status_code, resp.text[:200])
                return {"status": "failed", "error": f"composer returned {resp.status_code}"}, None
            summary = resp.json()["choices"][0]["message"]["content"].strip()
            logger.info("WHATSAPP summary: {}", summary[:120])
        except Exception as exc:
            logger.error("WHATSAPP composer failed: {}", exc)
            return {"status": "failed", "error": str(exc)}, None

        components = []
        if settings.whatsapp_header_media_id:
            components.append(
                {
                    "type": "header",
                    "parameters": [
                        {"type": "image", "image": {"id": settings.whatsapp_header_media_id}}
                    ],
                }
            )
        components.append(
            {
                "type": "body",
                "parameters": [
                    {"type": "text", "text": caller_name},
                    {"type": "text", "text": " ".join(summary.split())[:1024]},
                ],
            }
        )

        payload = {
            "messaging_product": "whatsapp",
            "to": wa_number,
            "type": "template",
            "template": {
                "name": settings.whatsapp_template_name,
                "language": {"code": "en"},
                "components": components,
            },
        }

        logger.info("WHATSAPP sending template to {}", wa_number)
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{WHATSAPP_GRAPH_API}/{settings.whatsapp_phone_number_id}/messages",
                    json=payload,
                    headers={"Authorization": f"Bearer {settings.whatsapp_access_token}"},
                )
            if resp.status_code >= 400:
                detail = resp.text[:300]
                logger.error("WHATSAPP send failed: {} {}", resp.status_code, detail)
                return {"status": "failed", "error": f"WhatsApp {resp.status_code}: {detail}"}, None
            msg_id = (resp.json().get("messages") or [{}])[0].get("id", "unknown")
            logger.info("WHATSAPP sent message_id={}", msg_id)
            return {
                "sent": True,
                "type": "template",
                "template": settings.whatsapp_template_name,
            }, None
        except Exception as exc:
            logger.error("WHATSAPP send failed: {}", exc)
            return {"sent": False, "error": str(exc)}, None

    # TODO: tool/create-contact
    # When a contact says "I'm not the right person, talk to X", ask for X's name, role, and phone number
    # and save to the CRM/database.
    # async def handle_create_contact(args: dict, flow_manager: FlowManager) -> tuple[dict, NodeConfig | None]:
    #     name = args.get("name")
    #     phone = args.get("phone")
    #     role = args.get("role", "Decision Maker")
    #     logger.info("CRM created referral contact: {} ({}) at {}", name, role, phone)
    #     return {"status": "contact_created", "name": name}, None

    tools_list.extend(
        [
            FlowsFunctionSchema(
                name="change_node",
                description="[tool/change-node] Switch to discovery, qualification, hot_pricing, warm_nurture, diplomatic_exit, callback_scheduling, or closing.",
                properties={"node": {"type": "string", "enum": list(VALID_NODES)}},
                required=["node"],
                handler=handle_change_node,
            ),
            FlowsFunctionSchema(
                name="end_call",
                description="[tool/end-call] Gracefully terminate the phone call when conversation concludes or caller requests to hang up.",
                properties={},
                required=[],
                handler=handle_end_call,
            ),
            FlowsFunctionSchema(
                name="send_whatsapp_template",
                description="[tool/send-whatsapp-template] Send pre-approved WhatsApp follow-up template with header image and summary.",
                properties={
                    "caller_name": {
                        "type": "string",
                        "description": "Caller's name as stated during the call.",
                    }
                },
                required=["caller_name"],
                handler=handle_send_whatsapp_template,
            ),
            FlowsFunctionSchema(
                name="send_followup",
                description="[tool/send-followup] Alias for send_whatsapp_template.",
                properties={
                    "caller_name": {
                        "type": "string",
                        "description": "Caller's name as stated during the call.",
                    }
                },
                required=["caller_name"],
                handler=handle_send_whatsapp_template,
            ),
            FlowsFunctionSchema(
                name="classify_jev",
                description="[tool/classify-jev] Run TypeSafe AI Jev System One multi-choice classification on the live call state to evaluate lead temperature probabilities, service fit, and tone.",
                properties={},
                required=[],
                handler=handle_classify_jev,
            ),
            FlowsFunctionSchema(
                name="classify_llm",
                description="[tool/classify-llm] Run fast LLM multi-choice categorization on the live call state to evaluate lead temperature, service fit, and tone.",
                properties={},
                required=[],
                handler=handle_classify_llm,
            ),
            FlowsFunctionSchema(
                name="classify_lead",
                description="[tool/classify-lead] Alias for classify_jev.",
                properties={},
                required=[],
                handler=handle_classify_jev,
            ),
        ]
    )

    return tools_list


NODE_TOOLS_MAP: dict[str, list[str]] = {
    "greeting": ["change_node", "end_call"],
    "discovery": ["change_node", "end_call"],
    "qualification": ["change_node", "end_call"],
    "hot_pricing": ["change_node", "end_call", "send_whatsapp_template", "send_followup"],
    "warm_nurture": ["change_node", "end_call", "send_whatsapp_template", "send_followup"],
    "diplomatic_exit": ["change_node", "end_call", "send_whatsapp_template", "send_followup"],
    "callback_scheduling": ["change_node", "end_call"],
    "closing": ["change_node", "end_call"],
}


def build_node(
    name: str = "greeting",
    tools_list: list[FlowsFunctionSchema] | None = None,
) -> NodeConfig:
    """Build a node configuration populated with scoped tools."""
    prompt = NODE_PROMPTS.get(name, NODE_PROMPTS["greeting"])
    functions = []
    if tools_list:
        allowed = NODE_TOOLS_MAP.get(name, [t.name for t in tools_list])
        functions = [t for t in tools_list if t.name in allowed]
    else:
        # Fallback default schema for change_node
        functions = [
            FlowsFunctionSchema(
                name="change_node",
                description="Switch conversation stage.",
                properties={"node": {"type": "string", "enum": list(VALID_NODES)}},
                required=["node"],
                handler=change_node,
            )
        ]

    return NodeConfig(
        name=name,
        role_message=prompt,
        task_messages=[],
        functions=functions,
        respond_immediately=True,
    )


# ==============================================================================
# 8. PIPELINE RUNTIME SETUP
# ==============================================================================


def build_services(settings: DemoProviderSettings, tts_provider: str = ACTIVE_TTS_PROVIDER):
    stt = SarvamSTTService(
        api_key=settings.sarvam_api_key,
        settings=SarvamSTTService.Settings(model=SARVAM_STT_MODEL),
        sample_rate=SAMPLE_RATE,
    )
    llm = GroqLLMService(
        api_key=settings.groq_api_key,
        settings=GroqLLMService.Settings(
            model=GROQ_MODEL,
            system_instruction=AGENT_SYSTEM_INSTRUCTION,
            reasoning_effort="none",
            temperature=AGENT_TEMPERATURE,
            max_tokens=AGENT_MAX_TOKENS,
        ),
    )
    if tts_provider.lower() == "sarvam":
        tts = SarvamTTSService(
            api_key=settings.sarvam_api_key,
            settings=SarvamTTSService.Settings(
                model=SARVAM_TTS_MODEL,
                voice=SARVAM_TTS_VOICE,
                language=SARVAM_TTS_LANGUAGE,
            ),
            sample_rate=SAMPLE_RATE,
        )
    else:
        tts = CartesiaTTSService(
            api_key=settings.cartesia_api_key,
            settings=CartesiaTTSService.Settings(voice=CARTESIA_VOICE_ID),
            sample_rate=SAMPLE_RATE,
            encoding="pcm_s16le",
            container="raw",
        )
    return stt, llm, tts


def build_pipeline(transport: BaseTransport, stt, llm, tts, probe=False):
    vad = SileroVADAnalyzer(
        sample_rate=SAMPLE_RATE,
        params=VADParams(
            confidence=VAD_CONFIDENCE,
            stop_secs=VAD_STOP_SECS,
            start_secs=VAD_START_SECS,
            min_volume=VAD_MIN_VOLUME,
        ),
    )
    context = LLMContext(
        [{"role": "user", "content": "Start the phone conversation with your friendly greeting."}]
    )
    aggregators = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=vad,
        ),
    )
    stages = [stt, aggregators.user(), llm, tts]
    if not probe:
        stages.insert(0, transport.input())
        stages.append(transport.output())
    stages.append(aggregators.assistant())
    pipeline = Pipeline(stages)
    return pipeline, aggregators, context


async def run_call(
    number: str, env_file: str = ".env", check: bool = False, probe: bool = False
) -> None:
    settings = DemoProviderSettings(_env_file=env_file)
    secrets = [
        s
        for s in [
            settings.cartesia_api_key,
            settings.sarvam_api_key,
            settings.groq_api_key,
            settings.jev_api_key,
        ]
        if s and s.strip()
    ]
    if not settings.sarvam_api_key.strip() or not settings.groq_api_key.strip():
        raise ValueError("Sarvam and Groq keys must be nonempty")
    if ACTIVE_TTS_PROVIDER == "cartesia" and not settings.cartesia_api_key.strip():
        raise ValueError("Cartesia API key must be nonempty when ACTIVE_TTS_PROVIDER is cartesia")
    directory = Path("data/recordings") / (
        datetime.now(UTC).strftime("%Y%m%d-%H%M%S-") + uuid4().hex[:8]
    )
    directory.mkdir(parents=True)

    def redact(record):
        for secret in secrets:
            record["message"] = record["message"].replace(secret, "<redacted>")
        return True

    logger.remove()
    logger.add(sys.stderr, level="INFO", filter=redact, diagnose=False, backtrace=False)
    sink = logger.add(
        directory / "pipeline.log", level="DEBUG", filter=redact, diagnose=False, backtrace=False
    )
    capture = CallCapture(directory, SAMPLE_RATE)
    logger.info("RUN capture={} check={} provider_probe={}", directory.resolve(), check, probe)
    logger.info(
        "CONFIG PCM={}Hz mono s16le frame={}ms VAD={} start={} stop={} volume={}",
        SAMPLE_RATE,
        FRAME_MS,
        VAD_CONFIDENCE,
        VAD_START_SECS,
        VAD_STOP_SECS,
        VAD_MIN_VOLUME,
    )
    stt, llm, tts = build_services(settings)
    bridge = Sim7600UsbAudioBridge(
        AUDIO_PORT,
        BAUDRATE,
        sample_rate=SAMPLE_RATE,
        channels=CHANNELS,
        capture=capture,
        frame_ms=FRAME_MS,
    )
    transport = bridge.transport()
    pipeline, aggregators, context = build_pipeline(transport, stt, llm, tts, probe=probe)

    sales_state: dict[str, Any] = {
        "whatsapp_window_open": False,
        "caller_name": "there",
        "jev_classification": None,
    }

    worker = PipelineWorker(
        pipeline,
        observers=[capture],
        enable_rtvi=False,
        params=PipelineParams(
            enable_metrics=True,
            audio_in_sample_rate=SAMPLE_RATE,
            audio_out_sample_rate=SAMPLE_RATE,
        ),
    )
    flow = FlowManager(
        worker=worker,
        llm=llm,
        context_aggregator=aggregators,
        transport=transport,
    )
    modem = Sim7600Modem(AT_PORT, BAUDRATE, command_timeout=AT_COMMAND_TIMEOUT)
    session = TelephonySession(modem)
    runner = WorkerRunner(handle_sigint=True)
    monitor = None
    call_attempted = False
    failures = []

    tools_list = _make_tools(settings, context, number, worker=worker, sales_state=sales_state)

    async def watch_call():
        started = asyncio.get_running_loop().time()
        try:
            while asyncio.get_running_loop().time() - started < MAX_CALL_SECONDS:
                await asyncio.sleep(1)
                try:
                    state = await modem.state()
                except Exception:
                    logger.info("CALL ended (modem reported disconnect)")
                    break
                if state != CallState.ACTIVE:
                    logger.info("CALL ended by remote")
                    break
            else:
                logger.info("CALL reached {} second limit", MAX_CALL_SECONDS)
        finally:
            await worker.cancel()

    @worker.event_handler("on_pipeline_started")
    async def ready(_worker, _frame):
        nonlocal monitor, call_attempted
        try:
            logger.info("PIPELINE ready; serial endpoint and providers initialized")
            if probe:

                async def finish_probe():
                    await asyncio.sleep(8)
                    await worker.cancel()

                monitor = asyncio.create_task(finish_probe())
                await flow.initialize(build_node("greeting", tools_list))
                return
            call_attempted = True
            await modem.ensure_pcm_format(SAMPLE_RATE)
            await session.start_call(number)
            logger.info("CALL active; starting greeting")
            await flow.initialize(build_node("greeting", tools_list))
            monitor = asyncio.create_task(watch_call())

        except Exception as exc:
            failures.append(str(exc))
            logger.error("STARTUP failed: {}", exc)
            await worker.cancel()

    @worker.event_handler("on_pipeline_error")
    async def error(_worker, frame):
        failures.append(str(frame.error))
        logger.error("PIPELINE error: {}", frame.error)
        await worker.cancel()

    try:
        build_node("greeting", tools_list)["functions"][0].to_function_schema()
        if check:
            await flow.initialize(build_node("greeting", tools_list))
            logger.info("CHECK passed: SDR persona, Jev engine, tools suite, flow initialization")
            return
        await runner.add_workers(worker)
        await runner.run()
    finally:
        if monitor:
            monitor.cancel()
            await asyncio.gather(monitor, return_exceptions=True)
        try:
            if call_attempted:
                await session.end_call()
        except Exception as exc:
            failures.append(str(exc))
            logger.error("CLEANUP failed: {}", exc)
        finally:
            await session.close()
            capture.close()
            logger.info("RUN ended errors={} artifacts={}", failures, directory.resolve())
            logger.remove(sink)
    if failures:
        raise RuntimeError("Call test failed; see pipeline.log")


def main() -> None:
    global SAMPLE_RATE
    parser = argparse.ArgumentParser(description="Run basic SIM7600 voice-path demo")
    parser.add_argument("--number", required=True, help="E.164 phone number to dial")
    parser.add_argument(
        "--sample-rate",
        type=int,
        default=SAMPLE_RATE,
        help="PCM sample rate in Hz (default: %(default)s). "
        "Use 16000 after sending AT+CPCMFRM=1 to the modem.",
    )
    parser.add_argument("--env-file", default=".env")
    parser.add_argument(
        "--probe-providers",
        action="store_true",
        help="Exercise provider pipeline for 8 seconds without opening modem ports or dialing",
    )
    parser.add_argument(
        "--check", action="store_true", help="Validate flow without modem or provider requests"
    )
    args = parser.parse_args()
    SAMPLE_RATE = args.sample_rate
    asyncio.run(run_call(args.number, args.env_file, args.check, args.probe_providers))


if __name__ == "__main__":
    main()
