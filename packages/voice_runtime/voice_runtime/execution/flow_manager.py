"""Pipecat flow transitions with ordered tool and classifier evidence."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import replace
from typing import Any

from pipecat.flows import FlowManager, NodeConfig
from pipecat.frames.frames import FunctionCallResultProperties
from pipecat.processors.aggregators.llm_context import LLMContext

from voice_runtime.diagnostics import exception_diagnostic
from voice_runtime.execution.classifier import model_visible_result, normalize_classifier_result
from voice_runtime.execution.exchange import ExchangeTracker
from voice_runtime.execution.observer import EvidenceObserver
from voice_runtime.execution.termination import CallTermination
from voice_runtime.execution.whatsapp_state import begin_send, finish_send


class TracedFlowManager(FlowManager):
    def __init__(
        self,
        *,
        tracker: ExchangeTracker,
        bindings: dict,
        snapshot: dict,
        observer: EvidenceObserver,
        context: LLMContext,
        classifier_runner: Callable[[str, str], Awaitable[tuple[str, dict[str, str]] | None]],
        end_call_runner: Callable[[], Awaitable[None]] | None = None,
        termination: CallTermination | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.tracker = tracker
        self.bindings = bindings
        self._snapshot = snapshot
        self.observer = observer
        self._context_for_evidence = context
        self._classifier_runner = classifier_runner
        self._end_call_runner = end_call_runner
        self.termination = termination
        self._transition_tool_id: str | None = None
        self.context_generation = 0
        self._current_node_task_messages: list[dict] = []
        self._active_tool_invocation: ContextVar[str | None] = ContextVar(
            f"active_tool_invocation_{id(self)}", default=None
        )

    @property
    def active_tool_invocation_id(self) -> str | None:
        return self._active_tool_invocation.get()

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
        self._current_node_task_messages = list(node_config.get("task_messages", []))
        self.tracker.start_visit(node_id, self._transition_tool_id)
        self._transition_tool_id = None
        try:
            await super()._set_node(node_id, node_config)
            self.context_generation += 1
            if next(
                (
                    node.get("terminal", False)
                    for node in self._snapshot["flow"]["nodes"]
                    if node["id"] == node_id
                ),
                False,
            ):
                if self.termination is not None:
                    self.termination.summary.terminal_node = node_id
        except BaseException:
            self.tracker.end_visit("failed")
            raise

    async def _create_transition_func(self, name, handler):
        execute = await super()._create_transition_func(name, handler)

        async def traced(params):
            binding = self.bindings.get(name)
            whatsapp = bool(
                binding
                and binding.get("definition", {}).get("handler")
                in {"send_whatsapp_template", "send_whatsapp_message"}
                and any(
                    slot.get("key") == "whatsapp_sent"
                    for slot in self._snapshot.get("fact_slots", [])
                )
            )
            previous_send = begin_send(self.state, name) if whatsapp else None
            invocation_id = self.tracker.start_tool(
                name,
                binding["version_id"] if binding else None,
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
            active_tool_token = self._active_tool_invocation.set(invocation_id)

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
                    if name == "classify_lead" and (
                        not isinstance(result, dict) or result.get("status") != "started"
                    ):
                        result = model_visible_result(
                            normalize_classifier_result(
                                result,
                                (
                                    self._snapshot.get("classifier", {}).get(
                                        "jev"
                                        if self._snapshot.get("classifier", {}).get(
                                            "classifier_type"
                                        )
                                        == "jev"
                                        else "llm",
                                        {},
                                    )
                                    or {}
                                ).get("output_fields"),
                                max_result_chars=int(
                                    self._snapshot.get("classifier", {}).get(
                                        "max_result_chars", 512
                                    )
                                ),
                            ),
                            int(self._snapshot.get("classifier", {}).get("max_result_chars", 512)),
                        )
                if whatsapp and is_final and isinstance(result, dict):
                    finish_send(self.state, name, result)
                if isinstance(diagnostic, dict):
                    self.tracker.diagnostic(**diagnostic)
                result_id = self.tracker.tool_result(invocation_id, result, is_final=is_final)
                if (name == "change_node" or name.startswith("go_to_")) and is_final:
                    self._transition_tool_id = invocation_id
                result_properties = properties or FunctionCallResultProperties(is_final=is_final)
                if (
                    name == "end_call"
                    and is_final
                    and isinstance(result, dict)
                    and result.get("status") == "ok"
                ):
                    result_properties = replace(result_properties, run_llm=False)
                previous_context_callback = result_properties.on_context_updated

                async def context_updated() -> None:
                    self.tracker.context_updated(
                        invocation_id,
                        result_id,
                        context_message_index=self._context_message_index(),
                    )
                    if previous_context_callback is not None:
                        await previous_context_callback()

                result_properties = replace(result_properties, on_context_updated=context_updated)
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
                if previous_send is not None:
                    await result_callback(previous_send)
                else:
                    await execute(replace(params, result_callback=result_callback))
            finally:
                self._active_tool_invocation.reset(active_tool_token)
                if not final_sent and not self.tracker.tool_was_ended(invocation_id):
                    self.tracker.end_tool(
                        invocation_id, "failed", {"error": "No final tool result"}
                    )
            # The tool result must be delivered before EndFrame can stop the worker.
            # Keep shutdown outside Flows' exception-to-tool-result conversion.
            if (
                name == "end_call"
                and final_sent
                and isinstance(final_result, dict)
                and final_result.get("status") == "ok"
                and self._end_call_runner is not None
            ):
                await self._end_call_runner()
            return final_result

        return traced
