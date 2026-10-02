"""Pipeline startup, lifecycle, termination, and safe teardown."""

from __future__ import annotations

import asyncio

from pipecat.flows import FlowManager
from pipecat.frames.frames import EndFrame, TTSSpeakFrame

from voice_runtime.diagnostics import (
    text_error_diagnostic,
)
from voice_runtime.safe_logs import RuntimeEvent, error_category, opaque_id, operational_event
from voice_runtime.telephony.base import CallState


class NativePipelineLifecycle:
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
        maximum = int(self._snapshot.get("idle_reprompt_limit", 1))
        if self._idle_reprompts < maximum:
            self._idle_reprompts += 1
            await self.worker.queue_frame(
                TTSSpeakFrame(
                    self._snapshot.get("idle_reprompt_text", "Are you still there?"),
                    append_to_context=True,
                )
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

    async def _pipeline_failed(self, frame) -> None:
        """A shutdown request does not make a subsequent pipeline failure successful."""
        self.termination.request("pipeline_failure")
        err_msg = getattr(frame, "error", None) or "inspect evidence"
        operational_event(
            RuntimeEvent.PIPELINE_FAILED,
            level="WARNING",
            status="failed",
            run_id=opaque_id(self.run_id),
        )
        self.errors.append("Pipeline failed; inspect structured diagnostics")
        if self.tracker is not None:
            self.tracker.diagnostic(**text_error_diagnostic(err_msg))
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
        async def _check_active() -> bool:
            if modem_or_check is None:
                return True
            if callable(modem_or_check) and not hasattr(modem_or_check, "state"):
                return await modem_or_check()
            # Legacy SIM modem path
            return await modem_or_check.state() == CallState.ACTIVE

        while self.runner_task and not self.runner_task.done():
            if self.capture:
                self.capture.check()
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
                detail=error_category(exc),
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
            detail=None,
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
            self._call_closed = True

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
                if self._background_tool_tasks:
                    pending = set(self._background_tool_tasks)
                    done, pending = await asyncio.wait(pending, timeout=5)
                    for task in pending:
                        task.cancel()
                    if pending:
                        await asyncio.gather(*pending, return_exceptions=True)
                    if done:
                        await asyncio.gather(*done, return_exceptions=True)
                for event in getattr(self, "pending_context", {}).values():
                    if event["status"] == "pending":
                        event["status"] = "ended_before_delivery"
                        if getattr(self, "broker", None):
                            await self.broker.context_update({"id": event["id"], "status": "ended_before_delivery"})
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
                    await asyncio.to_thread(attempt_cleanup, self.capture.close)

            if cleanup_error is not None:
                self.termination.summary.cleanup_status = "uncertain"
            self._close_attempted = True
            self._close_error = primary_error or cleanup_error
            if self._close_error is not None:
                raise self._close_error
