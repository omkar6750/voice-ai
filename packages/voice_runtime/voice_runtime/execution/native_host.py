"""DB-snapshot-driven Pipecat host for one voice call.

Transport-neutral: the caller injects a ready Pipecat BaseTransport.
This deliberately does not import the protected standalone demo.
"""

from __future__ import annotations

import asyncio
import math
from copy import deepcopy
from pathlib import Path
from typing import Any

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.flows import ContextStrategy, ContextStrategyConfig, NodeConfig
from pipecat.flows.types import FlowsFunctionSchema
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMAssistantAggregatorParams,
    LLMContextAggregatorPair,
)
from pipecat.services.google.llm import GoogleLLMService
from pipecat.services.groq.llm import GroqLLMService
from pipecat.utils.context.llm_context_summarization import (
    LLMAutoContextSummarizationConfig,
    LLMContextSummaryConfig,
)
from pipecat.workers.runner import WorkerRunner

from voice_runtime.call_capture import CallCapture
from voice_runtime.contracts import is_registered_handler, validate_node_actions
from voice_runtime.contracts.prompt_references import compile_tool_references
from voice_runtime.execution.classifier_runtime import NativeClassifierRuntime
from voice_runtime.execution.contact_context import sanitize_contact_variables
from voice_runtime.execution.context_delivery import NativeContextDelivery
from voice_runtime.execution.credential_keys import stage_api_key
from voice_runtime.execution.evidence_runtime import NativeEvidenceRuntime
from voice_runtime.execution.exchange import ExchangeTracker, bind_transcripts
from voice_runtime.execution.flow_manager import TracedFlowManager as TracedFlowManager
from voice_runtime.execution.native_helpers import (
    _CallerTurnContextEventProcessor as _CallerTurnContextEventProcessor,
)
from voice_runtime.execution.native_helpers import (
    build_user_aggregator_params as build_user_aggregator_params,
)
from voice_runtime.execution.native_helpers import (
    render_opening as render_opening,
)
from voice_runtime.execution.node_actions import NativeNodeActions
from voice_runtime.execution.observer import EvidenceObserver
from voice_runtime.execution.pipeline_lifecycle import NativePipelineLifecycle
from voice_runtime.execution.speech import build_speech_services as build_speech_services
from voice_runtime.execution.temporal import resolve_local_time_context
from voice_runtime.execution.termination import CallTermination
from voice_runtime.execution.tool_dispatch import NativeToolDispatch


class NativePipelineHost(
    NativeClassifierRuntime,
    NativeToolDispatch,
    NativeContextDelivery,
    NativeEvidenceRuntime,
    NativeNodeActions,
    NativePipelineLifecycle,
):
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
        self._background_tool_tasks: set[asyncio.Task] = set()
        self._call_closed = False
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
        callback_config = self._snapshot.get("callback_scheduling", {})
        callback_role_keys = {
            role.get("key")
            for role in callback_config.get("roles", [])
            if role.get("enabled", True)
            and any(
                person.get("enabled", True) and role.get("key") in person.get("roles", [])
                for person in callback_config.get("bookable_people", [])
            )
        }
        callback_tools_available = bool(callback_config.get("enabled") and callback_role_keys)
        node_bindings = [
            name
            for name in node["tool_bindings"]
            if (name != "change_node" or transitions)
            and (
                name not in {"check_callback_availability", "book_callback"}
                or callback_tools_available
            )
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
            description = tool["description"]
            if self._is_nonblocking_tool(name):
                description = (
                    description.rstrip()
                    + " This classification operation is nonblocking: the immediate result only confirms it started. "
                    + "A later evidence-backed update arrives on a subsequent caller turn. Do not claim completion before that update."
                )
            if name == "check_callback_availability":
                enabled_roles = [
                    role
                    for role in callback_config.get("roles", [])
                    if role.get("enabled", True) and role.get("key") in callback_role_keys
                ]
                role_property = properties.get("role")
                if isinstance(role_property, dict):
                    role_property["enum"] = [role["key"] for role in enabled_roles]
                    role_property["description"] = (
                        "Choose one configured callback role by key. "
                        + "; ".join(
                            f"{role['key']} ({role['label']}): {role['description']}"
                            for role in enabled_roles
                        )
                    )
                description = (
                    description.rstrip()
                    + " The backend assigns an eligible employee and calendar; do not ask the caller to choose an employee."
                )
            functions.append(
                FlowsFunctionSchema(
                    name=name,
                    description=description,
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

    async def prepare(
        self, snapshot: dict, tracker: ExchangeTracker, *, transport=None, enable_rtvi=False
    ) -> None:
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
                api_key=stage_api_key(self.settings, "llm", "groq"),
                settings=GroqLLMService.Settings(**llm_settings),
            )
        elif llm_config["provider"] == "gemini":
            if not self.settings.gemini_api_key:
                raise ValueError("Gemini API key is not configured")
            # Preserve provider-default thinking. No universal disable setting exists.
            llm = GoogleLLMService(
                api_key=stage_api_key(self.settings, "llm", "gemini"),
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
                    api_key=stage_api_key(self.settings, "summarizer", "groq"),
                    settings=GroqLLMService.Settings(
                        **summary_settings,
                        reasoning_effort="none",
                    ),
                )
            elif summary_provider == "gemini":
                summary_llm = GoogleLLMService(
                    api_key=stage_api_key(self.settings, "summarizer", "gemini"),
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
                _CallerTurnContextEventProcessor(self._deliver_pending_context_events, context),
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
        self.observer.context_event_consumer = self._mark_context_events_consumed
        self.worker = PipelineWorker(
            pipeline,
            observers=[self.observer, self.capture],
            enable_rtvi=enable_rtvi,
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
