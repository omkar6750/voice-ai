"""Termination observations retain cause independently of cleanup and playback."""

import pytest
from voice_runtime.execution.termination import CallTermination


def test_repeated_agent_close_has_one_identity_and_end_frame():
    call = CallTermination()
    assert call.request("agent_hangup", graceful=True)
    first = call.snapshot()
    assert not call.request("agent_hangup", graceful=True)
    assert call.snapshot() == first
    assert call.claim_end_frame()
    assert not call.claim_end_frame()


def test_pipeline_failure_during_goodbye_does_not_become_success():
    call = CallTermination()
    call.request("agent_hangup", graceful=True)
    call.request("pipeline_failure")
    call.pipeline_finished()
    assert call.summary.cause == "pipeline_failure"
    assert call.summary.execution_status == "failed"
    assert call.summary.mode == "immediate"
    call.request("agent_hangup", graceful=True)
    assert call.summary.cause == "pipeline_failure"


def test_cleanup_uncertainty_is_independent_of_call_cause():
    call = CallTermination()
    call.request("terminal_completed", graceful=True)
    call.pipeline_finished()
    call.summary.cleanup_status = "uncertain"
    assert call.summary.cause == "terminal_completed"
    assert call.summary.execution_status == "completed"
    assert call.snapshot()["cleanup_status"] == "uncertain"


def test_unknown_pipeline_end_does_not_invent_completion():
    call = CallTermination()
    call.pipeline_finished()
    assert call.summary.execution_status == "failed"
    assert call.summary.cause == "unknown"


@pytest.mark.parametrize("cause", ["caller_hangup", "disconnect_unknown", "unknown"])
def test_terminal_visit_counts_as_completed_without_rewriting_cause(cause):
    call = CallTermination()
    call.summary.terminal_node = "closing"
    call.request(cause)
    call.pipeline_finished()
    assert call.summary.execution_status == "completed"
    assert call.summary.evidence_status == "completed"
    assert call.summary.cause == cause


@pytest.mark.parametrize(
    "cause",
    [
        "pipeline_failure",
        "provider_failure",
        "evidence_failure",
        "duration_limit",
        "execution_lease_expired",
    ],
)
def test_terminal_visit_does_not_hide_execution_failure(cause):
    call = CallTermination()
    call.summary.terminal_node = "closing"
    call.request(cause)
    call.pipeline_finished()
    assert call.summary.execution_status == "failed"


def test_output_drain_is_local_playback_evidence():
    call = CallTermination()
    call.playback_started()
    call.playback_stopped()
    assert call.summary.playback_status == "drained"
    assert call.summary.playback_source == "pipecat_output"
    assert call.summary.cleanup_status == "unknown"


def test_interrupted_audio_cannot_be_reported_as_drained_by_late_stop():
    call = CallTermination()
    call.playback_started()
    call.playback_interrupted()
    call.playback_stopped()
    assert call.summary.playback_status == "interrupted"


def test_requested_close_is_not_completed_until_pipeline_finishes():
    call = CallTermination()
    call.request("agent_hangup", graceful=True)
    assert call.summary.execution_status == "failed"
    call.pipeline_finished()
    assert call.summary.execution_status == "completed"


def test_caller_interrupting_goodbye_keeps_intent_but_is_not_success():
    call = CallTermination()
    call.request("agent_hangup", graceful=True)
    call.playback_started()
    call.request("caller_hangup")
    call.pipeline_finished()
    assert call.summary.requested_cause == "agent_hangup"
    assert call.summary.cause == "caller_hangup"
    assert call.summary.execution_status == "failed"
    assert call.summary.evidence_status == "interrupted"


def test_failure_interrupts_playback_and_preserves_first_failure():
    call = CallTermination()
    call.request("agent_hangup", graceful=True)
    call.playback_started()
    call.request("pipeline_failure")
    call.request("network_failure")
    assert call.summary.cause == "pipeline_failure"
    assert call.summary.playback_status == "interrupted"


def test_late_disconnect_does_not_rewrite_finished_agent_close():
    call = CallTermination()
    call.request("agent_hangup", graceful=True)
    call.pipeline_finished()
    call.request("disconnect_unknown")
    assert call.summary.cause == "agent_hangup"
    assert call.summary.execution_status == "completed"


def test_cleanup_cancellation_preserves_first_external_cause():
    call = CallTermination()
    call.request("caller_hangup")
    call.request("cancelled")
    assert call.summary.cause == "caller_hangup"


def test_disconnect_escalates_close_but_does_not_rerun_termination():
    call = CallTermination()
    call.request("agent_hangup", graceful=True)
    call.playback_started()
    assert not call.request("disconnect_unknown")
    assert call.summary.mode == "immediate"
    assert call.summary.playback_status == "interrupted"


@pytest.mark.parametrize("cause", ["caller_hangup", "disconnect_unknown", "cancelled"])
def test_external_or_cancelled_call_leaves_interrupted_evidence(cause):
    call = CallTermination()
    call.request(cause)
    assert call.summary.execution_status == "failed"
    assert call.summary.evidence_status == "interrupted"


def test_duplicate_pipeline_finished_retains_original_timestamp():
    call = CallTermination()
    call.pipeline_finished()
    first = call.snapshot()
    call.pipeline_finished()
    assert call.snapshot() == first
