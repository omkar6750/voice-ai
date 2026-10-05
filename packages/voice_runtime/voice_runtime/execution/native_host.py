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
from pipecat.flows import NodeConfig
from pipecat.flows.types import NO_RESPONSE, TRANSITION_IN_YAML, FlowsFunctionSchema
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMAssistantAggregatorParams,
    LLMContextAggregatorPair,
)
from pipecat.utils.context.llm_context_summarization import (
    LLMAutoContextSummarizationConfig,
    LLMContextSummaryConfig,
)
from pipecat.workers.runner import WorkerRunner

from voice_runtime.call_capture import CallCapture
from voice_runtime.contracts import FactSlotConfig, is_registered_handler, validate_node_actions
from voice_runtime.contracts.prompt_references import compile_tool_references
from voice_runtime.execution.classifier_runtime import NativeClassifierRuntime
from voice_runtime.execution.contact_context import sanitize_contact_variables
from voice_runtime.execution.context_delivery import NativeContextDelivery
from voice_runtime.execution.credential_keys import stage_api_key
from voice_runtime.execution.evidence_runtime import NativeEvidenceRuntime
from voice_runtime.execution.exchange import ExchangeTracker, bind_transcripts
from voice_runtime.execution.flow_manager import TracedFlowManager as TracedFlowManager
from voice_runtime.execution.llm_factory import build_llm_service
from voice_runtime.execution.native_helpers import (
    _CallerTurnContextEventProcessor as _CallerTurnContextEventProcessor,
)
from voice_runtime.execution.native_helpers import (
    build_user_aggregator_params as build_user_aggregator_params,
)
from voice_runtime.execution.node_actions import NativeNodeActions
from voice_runtime.execution.observer import EvidenceObserver
from voice_runtime.execution.pipecat_flow import compile_pipecat_flow
from voice_runtime.execution.pipeline_lifecycle import NativePipelineLifecycle
from voice_runtime.execution.speech import build_speech_services as build_speech_services
from voice_runtime.execution.temporal import resolve_local_time_context
from voice_runtime.execution.termination import CallTermination
from voice_runtime.execution.tool_dispatch import NativeToolDispatch


def text_commit(output):
    return output.commit_processor()


def text_user_params():
    from pipecat.processors.aggregators.llm_response_universal import LLMUserAggregatorParams
    from pipecat.turns.user_turn_strategies import ExternalUserTurnStrategies

    return LLMUserAggregatorParams(
        user_turn_strategies=ExternalUserTurnStrategies(), user_idle_timeout=0
    )


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
        self.broker = None
        self.pending_context = {}
        self.worker = self.flow = self.capture = self.observer = None
        self.trace = None
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
        self._pipecat_flow = None
        self._global_function_keys: set[str] = set()
        self._flow_nodes_enriched = False
        self._compiled_global_functions: list[FlowsFunctionSchema] = []
        self._snapshot: dict = {}
        self._exchange_count = 0
        self._classifier_cadence_running = False
        self._background_tool_tasks: set[asyncio.Task] = set()
        self._call_closed = False
        self._close_lock = asyncio.Lock()
        self._close_attempted = False
        self._close_error: BaseException | None = None

    def _node(self, key: str) -> NodeConfig:
        """Add versioned application tools to Pipecat's compiled native node."""
        if self._flow_nodes_enriched:
            return dict(self._pipecat_flow.node(key))
        node = self._nodes[key]
        if self._pipecat_flow is None:
            self._pipecat_flow = compile_pipecat_flow(self._snapshot)
        transitions = node.get("transitions", [])
        config = dict(self._pipecat_flow.node(key))
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
        direct_functions = {
            function["name"] if isinstance(function, dict) else function.name
            for function in node.get("functions", [])
            if not (
                function.get("transition_only")
                if isinstance(function, dict)
                else function.transition_only
            )
        }
        node_bindings = [
            name
            for name in [*node["tool_bindings"], *direct_functions]
            if name not in node["tool_bindings"] or name not in direct_functions
            if name != "change_node"
            and name not in self._global_function_keys
            and (
                name not in {"check_callback_availability", "book_callback"}
                or callback_tools_available
            )
        ]
        exposed_tools = (
            set(node_bindings)
            | self._global_function_keys
            | {f"go_to_{target}" for target in transitions}
            | {
                f"record_{slot['key']}"
                for slot in self._snapshot.get("fact_slots", [])
                if not slot.get("nodes") or key in slot["nodes"]
            }
        )
        config["role_message"] = compile_tool_references(
            config.get("role_message", ""), exposed_tools
        )
        config["task_messages"] = [
            {
                "role": message["role"],
                "content": compile_tool_references(message["content"], exposed_tools),
            }
            for message in config.get("task_messages", [])
        ]
        bindings = self._snapshot["_resolved"]["tools"]
        functions = []
        for name in node_bindings:
            tool = bindings[name]["definition"]
            parameters = tool["parameters"]
            properties = deepcopy(parameters.get("properties", {}))
            required = parameters.get("required", [])
            if name == "change_node":
                node_property = properties.get("node")
                if isinstance(node_property, dict):
                    node_property["enum"] = list(transitions)
            description = tool["description"]
            if self._composer_template(name):
                from voice_runtime.execution.whatsapp_composer import composer_tool_schema

                properties, required, description = composer_tool_schema(tool)
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
                    required=required,
                    handler=(
                        next(
                            function.handler
                            for function in config.get("functions", [])
                            if (function["name"] if isinstance(function, dict) else function.name)
                            == name
                        )
                        if any(
                            (function["name"] if isinstance(function, dict) else function.name)
                            == name
                            and not (
                                function.get("transition_only")
                                if isinstance(function, dict)
                                else function.transition_only
                            )
                            for function in node.get("functions", [])
                        )
                        else self._handler(name)
                    ),
                )
            )
        merged_functions = {function.name: function for function in config.get("functions", [])}
        merged_functions.update({function.name: function for function in functions})
        config["functions"] = list(merged_functions.values())
        for slot_data in self._snapshot.get("fact_slots", []):
            if slot_data.get("nodes") and key not in slot_data["nodes"]:
                continue
            slot = FactSlotConfig.model_validate(slot_data)

            async def record_fact(args, manager, slot=slot):
                try:
                    value = slot.validate_value(args.get("value"))
                except (TypeError, ValueError) as exc:
                    return {"status": "error", "error": str(exc)}
                if slot.key == "whatsapp_sent":
                    from voice_runtime.execution.whatsapp_state import record_send_fact

                    return record_send_fact(manager.state, value)
                manager.state[slot.key] = value
                return {"status": "ok", "key": slot.key, "value": value}

            value_schema: dict[str, Any] = {
                "type": slot.value_type,
                "description": slot.description,
            }
            if slot.enum is not None:
                value_schema["enum"] = slot.enum
            if slot.minimum is not None:
                value_schema["minimum"] = slot.minimum
            if slot.maximum is not None:
                value_schema["maximum"] = slot.maximum
            config["functions"].append(
                FlowsFunctionSchema(
                    name=f"record_{slot.key}",
                    description=f"Record the caller's {slot.description} as a conversation fact.",
                    properties={"value": value_schema},
                    required=["value"],
                    handler=record_fact,
                )
            )
        function_names = [function.name for function in config.get("functions", [])]
        if len(set(function_names)) != len(function_names):
            raise ValueError(f"Pipecat function names collide in node '{key}'")
        if node.get("terminal"):
            # Pipecat serializes this control frame behind synthesis and local
            # output audio. It is not a claim of browser/carrier playback.
            config["post_actions"] = [
                *config.get("post_actions", []),
                {"type": "function", "handler": self._terminal_response_finished, "node": key},
            ]
        return config

    async def _run_configured_node_action(self, action: dict, _manager) -> None:
        """Execute a registry-backed action from a native Pipecat function action."""
        phase = action.get("phase", "entry")
        node_id = action.get("node_id")
        binding_key = action.get("binding_key")
        if phase not in {"entry", "exit"} or node_id not in self._nodes or not binding_key:
            raise ValueError("Configured Pipecat function action is invalid")
        await self._run_node_action(phase, node_id, binding_key)

    def _global_function_schemas(self) -> list[FlowsFunctionSchema]:
        """Resolve configured shared tools once for FlowManager(global_functions=...)."""
        if self._compiled_global_functions:
            return list(self._compiled_global_functions)
        if not self._global_function_keys:
            return []
        configured = [
            function
            for function in self._pipecat_flow.global_functions
            if function.name in self._global_function_keys
        ]
        missing = self._global_function_keys - {function.name for function in configured}
        if missing:
            raise ValueError(f"global functions are unavailable: {sorted(missing)}")
        return [
            self._registry_function_schema(function.name, function.handler)
            for function in configured
        ]

    def _registry_function_schema(self, name: str, handler) -> FlowsFunctionSchema:
        tool = self._snapshot["_resolved"]["tools"][name]["definition"]
        if name == "classify_lead":
            from voice_runtime.contracts.registry import registered_handler_specs

            spec = next(spec for spec in registered_handler_specs() if spec.name == name)
            tool = {"description": spec.description, "parameters": spec.parameters}
        if self._composer_template(name):
            from voice_runtime.execution.whatsapp_composer import composer_tool_schema

            properties, required, description = composer_tool_schema(tool)
        else:
            properties = deepcopy(tool["parameters"].get("properties", {}))
            required = tool["parameters"].get("required", [])
            description = tool["description"]
        return FlowsFunctionSchema(
            name=name,
            description=description,
            properties=properties,
            required=required,
            handler=handler,
        )

    def _composer_template(self, name: str) -> dict | None:
        composer = self._snapshot.get("composer") or {}
        return (composer.get("templates") or {}).get(name) if composer.get("enabled") else None

    def _pipecat_tool_proxy(self, name: str):
        async def proxy(flow_manager, **params):
            source_node = getattr(flow_manager, "current_node", None)
            result = await self._handler(name)(params, flow_manager)
            if isinstance(result, tuple):
                result = result[0]
            if name == "classify_lead" and flow_manager.current_node != source_node:
                return result, NO_RESPONSE
            if (
                name == "classify_lead"
                and self._snapshot.get("classifier", {}).get("routing_policy") == "lead_followup"
            ):
                from voice_runtime.execution.lead_routing import followup_route

                route = followup_route(result)
                # A failed result stays in place; an old result cannot change a newer node.
                if flow_manager.current_node != source_node:
                    return result, NO_RESPONSE
                if route is None:
                    return {
                        **(result if isinstance(result, dict) else {}),
                        "followup_route": "stay",
                    }, TRANSITION_IN_YAML
                result = {**result, "followup_route": route}
                self.tracker.diagnostic(
                    severity="info",
                    category="classifier_routing",
                    source="runtime",
                    code="lead_followup_route",
                    message="Classifier selected follow-up path",
                    detail=f"{source_node} -> {route}",
                )
            if name == "classify_lead" and (
                not isinstance(result, dict) or result.get("status") == "error"
            ):
                return result, NO_RESPONSE
            return result, TRANSITION_IN_YAML

        proxy.__name__ = name
        proxy.__doc__ = f"Run the versioned application tool {name}."
        return proxy

    def _local_observers(self):
        if not self.trace:
            return []
        from voice_runtime.execution.local_observer import (
            LocalErrorObserver,
            LocalLifecycleObserver,
        )

        return [LocalLifecycleObserver(self.trace), LocalErrorObserver(self.trace)]

    async def prepare(
        self,
        snapshot: dict,
        tracker: ExchangeTracker,
        *,
        transport=None,
        enable_rtvi=False,
        text_output=None,
    ) -> None:
        self.tracker, self._snapshot = tracker, snapshot
        self._nodes = {node["id"]: node for node in snapshot["flow"]["nodes"]}
        self._global_function_keys = {
            function["name"] if isinstance(function, dict) else function
            for function in snapshot["flow"].get("global_functions", [])
        }
        tool_handlers = {
            name: self._pipecat_tool_proxy(name)
            for node in snapshot["flow"].get("nodes", [])
            for function in node.get("functions", [])
            for name in [function["name"]]
            if not function.get("transition_only")
        }
        tool_handlers.update(
            {name: self._pipecat_tool_proxy(name) for name in self._global_function_keys}
        )
        self._pipecat_flow = compile_pipecat_flow(
            snapshot,
            handlers={
                "_run_configured_node_action": self._run_configured_node_action,
                **tool_handlers,
            },
        )
        self._compiled_global_functions = self._global_function_schemas()
        compiled_nodes = {key: self._node(key) for key in self._nodes}
        for key, node_config in compiled_nodes.items():
            self._pipecat_flow.node(key).update(node_config)
        self._flow_nodes_enriched = True
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
        composer_config = snapshot.get("composer") or {}
        if composer_config.get("enabled"):
            from voice_runtime.execution.whatsapp_composer import composer_fields

            for binding_key in composer_config.get("templates") or {}:
                binding = snapshot["_resolved"]["tools"].get(binding_key)
                if not binding or binding["definition"].get("handler") != "send_whatsapp_template":
                    raise ValueError(
                        f"Composer template '{binding_key}' is not a bound WhatsApp template"
                    )
                composer_fields(binding["definition"])
        for key in self._nodes:
            for name in self._nodes[key]["tool_bindings"]:
                if name not in snapshot["_resolved"]["tools"]:
                    raise ValueError("Node references unavailable tool binding")
        self.text_output = text_output
        required_credentials = (
            []
            if text_output
            else [
                (
                    f"stt:{snapshot['stt']['provider']}",
                    stage_api_key(self.settings, "stt", snapshot["stt"]["provider"]),
                )
            ]
        )
        llm_provider = snapshot["llm"]["provider"]
        required_credentials.append(
            (f"llm:{llm_provider}", stage_api_key(self.settings, "llm", llm_provider))
        )
        fallback = snapshot["llm"].get("fallback")
        if fallback:
            fallback_provider = fallback["provider"]
            required_credentials.append(
                (
                    f"llm_fallback:{fallback_provider}",
                    stage_api_key(self.settings, "llm_fallback", fallback_provider),
                )
            )
        classifier_cfg = snapshot.get("classifier", {})
        if classifier_cfg.get("enabled", True) and classifier_cfg.get("classifier_type") == "jev":
            required_credentials.append(
                ("jev_api_key", getattr(self.settings, "jev_api_key", None))
            )
        elif classifier_cfg.get("enabled", True):
            classifier_provider = (classifier_cfg.get("llm") or {}).get("provider", "groq")
            required_credentials.append(
                (
                    f"classifier:{classifier_provider}",
                    stage_api_key(self.settings, "classifier", classifier_provider),
                )
            )
        summarizer_cfg = snapshot.get("context", {}).get("summarizer", {})
        if summarizer_cfg.get("enabled"):
            summary_provider = (summarizer_cfg.get("model") or {}).get("provider", llm_provider)
            required_credentials.append(
                (
                    f"summarizer:{summary_provider}",
                    stage_api_key(self.settings, "summarizer", summary_provider),
                )
            )
        if composer_config.get("enabled"):
            composer_provider = (composer_config.get("model") or {}).get("provider", "groq")
            required_credentials.append(
                (
                    f"composer:{composer_provider}",
                    stage_api_key(self.settings, "composer", composer_provider),
                )
            )
        for name, value in required_credentials:
            if not value:
                raise ValueError(f"{name} is not configured")
        tts_provider = snapshot["tts"]["provider"]
        if text_output is None and not stage_api_key(self.settings, "tts", tts_provider):
            raise ValueError(f"tts:{tts_provider} is not configured")
        rate = snapshot["audio"]["sample_rate"]
        self.directory.mkdir(parents=True, exist_ok=True)
        self.capture = None if text_output else CallCapture(self.directory, rate)
        if transport is None and text_output is None:
            # Legacy SIM7600 path: construct transport from endpoint config.
            endpoint = snapshot["_resolved"]["endpoint"]
            from voice_runtime.telephony.usb_audio import Sim7600UsbAudioBridge

            transport = Sim7600UsbAudioBridge(
                endpoint["audio_port"],
                endpoint["baudrate"],
                trace=self.trace,
                sample_rate=rate,
                channels=1,
                capture=self.capture,
                frame_ms=snapshot["audio"]["frame_ms"],
            ).transport()
        stt, tts = (
            (None, None) if text_output else build_speech_services(self.settings, snapshot, rate)
        )
        llm_config = snapshot["llm"]
        llm = build_llm_service(
            self.settings,
            llm_config,
            stage="llm",
            system_instruction=snapshot["system_prompt"],
        )

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
            summary_llm = build_llm_service(
                self.settings,
                {
                    **summary_model,
                    **summary_settings,
                    "provider": summary_provider,
                    "reasoning_effort": "none",
                },
                stage="summarizer",
            )

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
        if text_output:
            vad = None
        else:
            # Sarvam Realtime owns turn boundaries for saaras:v4. Pipecat
            # still requires local Silero VAD on the user aggregator for
            # speech timing/TTFB measurements.
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
        for slot in snapshot.get("fact_slots", []):
            flow_state.setdefault(slot["key"], "")
        for variable in allowed_vars:
            flow_state.setdefault(variable, "")

        # Opening behavior belongs to the initial node's system instruction. Do not
        # synthesize a user turn or speak a separate verbatim greeting here.
        context = LLMContext([])
        self.context = context
        aggregators = LLMContextAggregatorPair(
            context,
            user_params=text_user_params()
            if text_output
            else build_user_aggregator_params(snapshot, vad),
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
        self.aggregators = aggregators
        pipeline = Pipeline(
            [
                aggregators.user(),
                _CallerTurnContextEventProcessor(self._deliver_pending_context_events, context),
                llm,
                text_output,
                aggregators.assistant(),
                text_commit(text_output),
            ]
            if text_output
            else [
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
            observers=[self.observer]
            + ([self.capture] if self.capture else [])
            + self._local_observers(),
            enable_rtvi=enable_rtvi,
            # Text sessions have no audio activity for Pipecat's default watchdog.
            # Runtime duration, disconnect and execution leases own text limits.
            **({"idle_timeout_secs": None} if text_output else {}),
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
            global_functions=self._global_function_schemas(),
            classifier_runner=self._run_node_classifier,
            end_call_runner=self._finish_end_call,
        )
        self.flow.state.update(flow_state)
        if text_output:
            text_output.host = self
            for key in self._nodes:
                for function in self._pipecat_flow.node(key).get("functions", []):
                    function.cancel_on_interruption = False
            for function in self._compiled_global_functions:
                function.cancel_on_interruption = False

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
