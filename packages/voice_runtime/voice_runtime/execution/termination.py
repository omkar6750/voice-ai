"""Call termination facts, independent of pipeline and transport cleanup.

Pipeline completion never proves who ended a call or that transport was released.
"""

from __future__ import annotations

import time
from typing import Literal
from uuid import uuid4

from pydantic import Field

from voice_runtime.contracts.base import ConfigModel

TerminationCause = Literal[
    "terminal_completed",
    "agent_hangup",
    "caller_hangup",
    "disconnect_unknown",
    "network_failure",
    "provider_failure",
    "pipeline_failure",
    "cancelled",
    "caller_idle_timeout",
    "duration_limit",
    "unknown",
]


class TerminationSummary(ConfigModel):
    termination_id: str = Field(default_factory=lambda: uuid4().hex)
    cause: TerminationCause = "unknown"
    requested_cause: TerminationCause = "unknown"
    mode: Literal["graceful", "immediate"] = "immediate"
    requested_at_ns: int | None = None
    pipeline_finished_at_ns: int | None = None
    terminal_node: str | None = None
    playback_status: Literal["unknown", "speaking", "drained", "interrupted"] = "unknown"
    playback_source: str | None = None
    cleanup_status: Literal["unknown", "confirmed", "uncertain"] = "unknown"

    @property
    def execution_status(self) -> Literal["completed", "failed"]:
        completed = (
            self.cause in {"terminal_completed", "agent_hangup"}
            and self.pipeline_finished_at_ns is not None
        )
        return "completed" if completed else "failed"

    @property
    def evidence_status(self) -> Literal["completed", "interrupted", "failed"]:
        if self.execution_status == "completed":
            return "completed"
        if self.cause in {"caller_hangup", "disconnect_unknown", "cancelled"}:
            return "interrupted"
        return "failed"


class CallTermination:
    """Synchronous observations are atomic within the owning asyncio loop."""

    def __init__(self) -> None:
        self.summary = TerminationSummary()
        self.end_queued = False

    @property
    def closing(self) -> bool:
        return self.summary.requested_at_ns is not None

    def request(self, cause: TerminationCause, *, graceful: bool = False) -> bool:
        if not self.closing:
            self.summary.cause = cause
            self.summary.requested_cause = cause
            self.summary.mode = "graceful" if graceful else "immediate"
            self.summary.requested_at_ns = time.time_ns()
            return True
        failures = {"provider_failure", "pipeline_failure", "network_failure"}
        if cause in failures or (not graceful and self.summary.pipeline_finished_at_ns is None):
            # Preserve the first failure, but do not mistake an interrupted goodbye
            # for success merely because the agent requested it first.
            if self.summary.cause not in failures:
                self.summary.cause = cause
            self.summary.mode = "immediate"
            if self.summary.playback_status == "speaking":
                self.summary.playback_status = "interrupted"
        return False

    def claim_end_frame(self) -> bool:
        if self.end_queued:
            return False
        self.end_queued = True
        return True

    def playback_started(self) -> None:
        self.summary.playback_status = "speaking"

    def playback_stopped(self) -> None:
        if self.summary.playback_status == "speaking":
            self.summary.playback_status = "drained"
            self.summary.playback_source = "pipecat_output"

    def playback_interrupted(self) -> None:
        if self.summary.playback_status == "speaking":
            self.summary.playback_status = "interrupted"

    def pipeline_finished(self) -> None:
        if self.summary.pipeline_finished_at_ns is None:
            self.summary.pipeline_finished_at_ns = time.time_ns()

    def snapshot(self) -> dict:
        return self.summary.model_dump(mode="json")
