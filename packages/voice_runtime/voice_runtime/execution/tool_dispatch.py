"""Tool dispatch and integration credential resolution for the call host."""

from __future__ import annotations

import asyncio

from pipecat.flows import FlowManager

from voice_runtime.execution.classifier import normalize_classifier_result, run_selected_classifier
from voice_runtime.execution.credential_keys import stage_api_key
from voice_runtime.execution.native_helpers import (
    _extract_transcript,
    run_jev_classification,
)
from voice_runtime.safe_logs import RuntimeEvent, error_category, operational_event


class NativeToolDispatch:
    def _handler(self, name: str):
        async def execute(args: dict, _manager: FlowManager):
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
            if name == "classify_lead":
                transcript = _extract_transcript(getattr(self, "context", None), self.tracker)
                classifier_cfg = self._snapshot.get("classifier", {})

                async def jev_request(**kwargs):
                    jev_cfg = kwargs["config"]
                    questions = jev_cfg.get("questions") or {}
                    if not questions:
                        from voice_runtime.contracts.cadence import default_jev_questions

                        questions = {k: v.model_dump() for k, v in default_jev_questions().items()}
                    jev_key = stage_api_key(self.settings, "classifier", "jev") or ""
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

            broker = getattr(self, "broker", None)
            if broker is None:
                return {"status": "error", "error": "Business tool broker unavailable"}
            invocation_id = getattr(_manager, "active_tool_invocation_id", None)
            return await broker.tool(name, args, invocation_id)

        async def handle(args: dict, manager: FlowManager):
            current_node = getattr(manager, "current_node", None)
            graph = self._snapshot.get("flow", {})
            route_functions = list(graph.get("global_functions", []))
            route_functions.extend(
                function
                for node in graph.get("nodes", [])
                if node.get("id") == current_node
                for function in node.get("functions", [])
            )
            classifier_routes = name == "classify_lead" and any(
                isinstance(function, dict)
                and function.get("name") == name
                and function.get("transition_to") is not None
                for function in route_functions
            )
            if (
                not self._is_nonblocking_tool(name)
                or classifier_routes
                or self._snapshot.get("classifier", {}).get("routing_policy") == "lead_followup"
            ):
                return await execute(args, manager)
            invocation_id = getattr(manager, "active_tool_invocation_id", None)
            if not invocation_id or self.tracker is None:
                return {"status": "error", "error": "Tool operation could not be initialized"}
            operation = self.tracker.start_operation(
                name,
                "tool",
                input_payload={"arguments": args},
                parent_operation_id=(
                    self.observer.llm_operation["operation_id"]
                    if self.observer and self.observer.llm_operation
                    else None
                ),
                asynchronous=True,
            )
            task = asyncio.create_task(
                self._run_background_tool(name, args, manager, invocation_id, operation, execute),
                name=f"async-tool-{name}-{invocation_id}",
            )
            self._background_tool_tasks.add(task)
            task.add_done_callback(self._background_tool_tasks.discard)
            return {
                "status": "started",
                "operation_id": operation["operation_id"],
                "message": "The operation has started. Do not claim its outcome until a later update confirms it.",
            }

        return handle

    @staticmethod
    def _is_nonblocking_tool(name: str) -> bool:
        return name == "classify_lead"

    async def _run_background_tool(self, name, args, manager, invocation_id, operation, execute):
        try:
            result = await execute(args, manager)
        except asyncio.CancelledError:
            self.tracker.finish_operation(
                operation,
                "interrupted",
                output_state="interrupted",
                failure_reason="host_shutdown_outcome_uncertain",
            )
            await self._persist_context_event(
                invocation_id,
                f"tool-result:{operation['operation_id']}",
                "tool_result",
                operation["operation_id"],
                {
                    "tool": name,
                    "result": {
                        "status": "uncertain",
                        "message": "The call ended before this operation's outcome was confirmed. Do not assume it succeeded or retry automatically.",
                    },
                },
            )
            raise
        except Exception as exc:
            operational_event(
                RuntimeEvent.TOOL_FAILED, level="ERROR", error_category=error_category(exc)
            )
            result = {
                "status": "error",
                "error": "The operation failed; details are in run diagnostics.",
            }
            self.tracker.finish_operation(
                operation, "failed", output_payload=result, output_state="failed"
            )
            self.tracker.diagnostic(
                severity="error",
                category="async_tool_failure",
                source="runtime",
                code="async_tool_failed",
                message="Asynchronous tool execution failed",
                detail=error_category(exc),
            )
            connection_id = provider_message_id = None
        else:
            connection_id = result.pop("_connection_id", None) if isinstance(result, dict) else None
            provider_message_id = (
                result.pop("_provider_message_id", None) if isinstance(result, dict) else None
            )
            if name == "classify_lead" and isinstance(result, dict):
                from voice_runtime.execution.classifier import model_visible_result

                max_chars = int(self._snapshot.get("classifier", {}).get("max_result_chars", 512))
                result = model_visible_result(result, max_chars)
            result = self._bounded_context_result(result)
            failed = isinstance(result, dict) and result.get("status") == "error"
            self.tracker.finish_operation(
                operation,
                "failed" if failed else "completed",
                output_payload=result,
                output_state="failed" if failed else "recorded",
            )
        try:
            await self._persist_context_event(
                invocation_id,
                f"tool-result:{operation['operation_id']}",
                "tool_result",
                operation["operation_id"],
                {"tool": name, "result": result},
                connection_id=connection_id,
                provider_message_id=provider_message_id,
            )
        except Exception:
            operational_event(RuntimeEvent.EVIDENCE_FAILED, level="ERROR")
            self.tracker.diagnostic(
                severity="error",
                category="context_event_persistence",
                source="evidence",
                code="async_result_not_persisted",
                message="Asynchronous tool result could not be queued for context",
                uncertain=False,
            )
