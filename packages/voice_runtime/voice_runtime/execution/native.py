"""DB-snapshot-driven Pipecat host for one SIM7600 call.

This deliberately does not import the protected standalone demo.
"""

from __future__ import annotations

import asyncio
import os
import re
from dataclasses import replace
from pathlib import Path
from typing import Any

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
from pipecat.workers.runner import WorkerRunner

from voice_runtime.call_capture import CallCapture
from voice_runtime.execution.exchange import ExchangeTracker, bind_transcripts
from voice_runtime.execution.observer import EvidenceObserver
from voice_runtime.telephony.base import CallState
from voice_runtime.telephony.usb_audio import Sim7600UsbAudioBridge


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
        self._end_task: asyncio.Task | None = None
        self.tracker: ExchangeTracker | None = None
        self._nodes: dict[str, dict] = {}
        self._snapshot: dict = {}

    def _node(self, key: str) -> NodeConfig:
        node = self._nodes[key]
        flow = self._snapshot["flow"]
        prompt = node["prompt"]
        if flow["prompt_composition"] == "global_plus_node":
            prompt = self._snapshot["system_prompt"] + "\n\n" + prompt
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
            role_message=prompt,
            task_messages=[],
            functions=functions,
            respond_immediately=node["respond_immediately"],
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
                self._end_task = asyncio.create_task(self.worker.cancel())
                return {"status": "ok"}
            if name in ("send_whatsapp_template", "send_followup", "send_whatsapp_message"):
                access_token = getattr(self.settings, "whatsapp_access_token", None) or os.getenv(
                    "VOICE_WHATSAPP_ACCESS_TOKEN", ""
                )
                phone_number_id = getattr(
                    self.settings, "whatsapp_phone_number_id", None
                ) or os.getenv("VOICE_WHATSAPP_PHONE_NUMBER_ID", "")
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
                    contact.get("phone_number")
                    or contact.get("phone_e164")
                    or self._snapshot.get("target_snapshot", "")
                )
                recipient = re.sub(r"[^\d]", "", raw_phone)
                if not recipient:
                    logger.warning("No recipient phone number available for WhatsApp dispatch")
                    return {"status": "error", "error": "No valid phone number for contact"}

                caller_name = (args.get("caller_name") or contact.get("name") or "there").strip()
                template_name = getattr(self.settings, "whatsapp_template_name", None) or os.getenv(
                    "VOICE_WHATSAPP_TEMPLATE_NAME", "dialtone_followup"
                )
                header_media_id = getattr(
                    self.settings, "whatsapp_header_media_id", None
                ) or os.getenv("VOICE_WHATSAPP_HEADER_MEDIA_ID", "")

                summary = f"Thank you for speaking with Northstar Software Studio, {caller_name}! We have prepared your custom development overview and pricing catalog."
                if name == "send_followup" and args.get("message"):
                    summary = args["message"]

                components = []
                if header_media_id:
                    components.append(
                        {
                            "type": "header",
                            "parameters": [{"type": "image", "image": {"id": header_media_id}}],
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
                    "to": recipient,
                    "type": "template",
                    "template": {
                        "name": template_name,
                        "language": {"code": "en"},
                        "components": components,
                    },
                }

                try:
                    logger.info("WHATSAPP sending template '{}' to {}", template_name, recipient)
                    async with httpx.AsyncClient(timeout=10) as client:
                        resp = await client.post(
                            f"https://graph.facebook.com/v21.0/{phone_number_id}/messages",
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
                        return {"status": "ok", "message_id": msg_id}
                except Exception as exc:
                    logger.error("WhatsApp dispatch exception: {}", exc)
                    return {"status": "error", "error": f"WhatsApp request failed: {exc}"}

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
        llm = GroqLLMService(
            api_key=self.settings.groq_api_key,
            settings=GroqLLMService.Settings(**llm_settings),
        )
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
        context = LLMContext(
            [
                {
                    "role": "user",
                    "content": snapshot["greeting"]
                    or "Start the phone conversation with your friendly greeting.",
                }
            ]
        )
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
        contact = snapshot["_resolved"].get("contact", {})
        self.flow.state["contact"] = contact
        for variable in snapshot.get("contact_variables", []):
            if variable in contact:
                self.flow.state[variable] = contact[variable]

        @self.worker.event_handler("on_pipeline_started")
        async def started(_worker, _frame):
            self.ready.set()

        @self.worker.event_handler("on_pipeline_error")
        async def failed(_worker, frame):
            self.errors.append("Pipeline failed; inspect evidence")
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
            if self.errors:
                raise RuntimeError(self.errors[-1])
            await asyncio.sleep(1)
            if await modem.state() != CallState.ACTIVE:
                await self.worker.cancel()
                break
        if self.runner_task:
            await self.runner_task
        if self.errors:
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
