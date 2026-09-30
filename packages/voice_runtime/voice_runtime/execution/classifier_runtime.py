"""Classifier execution and outcome handling for the native call host."""

from __future__ import annotations

from typing import Any

from voice_runtime.execution.classifier import normalize_classifier_result, run_selected_classifier
from voice_runtime.execution.credential_keys import stage_api_key
from voice_runtime.execution.native_helpers import _extract_transcript, run_jev_classification
from voice_runtime.safe_logs import RuntimeEvent, error_category, operational_event


class NativeClassifierRuntime:
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
                jev_key = stage_api_key(self.settings, "classifier", "jev") or ""
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
        except Exception as exc:
            operational_event(
                RuntimeEvent.CLASSIFIER_FAILED, level="ERROR", error_category=error_category(exc)
            )
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
