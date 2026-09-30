"""Execution of configured, allow-listed node actions."""

from __future__ import annotations

from uuid import uuid4

from voice_runtime.safe_logs import error_category


class NativeNodeActions:
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
                message="Configured node action failed",
                metadata={"error_category": error_category(exc)},
            )
            raise
        return False
