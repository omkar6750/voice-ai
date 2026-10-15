# ISSUE-006 Call release reason was unknown or over-attributed

Status: Implemented evidence model; some causes remain unknown. Reviewed October 15, 2026.

## Observed problem

NO CARRIER, missing CEER/network readings and an empty call list were insufficient to determine who ended a call. Local stop, modem I/O failure and remote release could look similar.

## Implemented behavior

Retain bounded relevant modem observations, freeze release evidence, preserve missing readings and separate execution completion from release attribution. Display technical evidence only on demand.

## Source

- [packages/voice_runtime/voice_runtime/telephony/outcome.py](../../packages/voice_runtime/voice_runtime/telephony/outcome.py)
- [packages/voice_runtime/voice_runtime/telephony/sim7600.py](../../packages/voice_runtime/voice_runtime/telephony/sim7600.py)
- [apps/dashboard/src/pages/runs/status.tsx](../../apps/dashboard/src/pages/runs/status.tsx)

## Regression coverage

- [test_call_outcome_evidence.py](../../tests/unit/test_call_outcome_evidence.py) — `test_conservative_release_causes`.
- [test_call_outcome_evidence.py](../../tests/unit/test_call_outcome_evidence.py) — `test_missing_status_is_unknown_not_confirmed_registration_loss`.
- [test_call_outcome_evidence.py](../../tests/unit/test_call_outcome_evidence.py) — `test_other_side_release_when_local_hangup_absent_and_network_is_healthy`.
- [test_call_outcome_evidence.py](../../tests/unit/test_call_outcome_evidence.py) — `test_registration_loss_before_disconnect_is_classified_as_network_failure`.
- [test_call_outcome_evidence.py](../../tests/unit/test_call_outcome_evidence.py) — `test_other_side_release_requires_no_local_hangup_and_healthy_known_network`.
- [test_call_outcome_evidence.py](../../tests/unit/test_call_outcome_evidence.py) — `test_routine_at_poll_commands_do_not_emit_operational_log_lines`.
- [test_call_outcome_evidence.py](../../tests/unit/test_call_outcome_evidence.py) — `test_idle_reader_records_call_urcs_only_and_preserves_release_before_cleanup`.
- [test_call_outcome_evidence.py](../../tests/unit/test_call_outcome_evidence.py) — `test_monitor_and_command_have_single_serial_reader`.
- [test_call_outcome_evidence.py](../../tests/unit/test_call_outcome_evidence.py) — `test_busy_call_never_enters_conversation_and_updates_shared_termination`.
- [test_call_outcome_evidence.py](../../tests/unit/test_call_outcome_evidence.py) — `test_connection_deadline_does_not_claim_carrier_no_answer`.
- [test_call_outcome_evidence.py](../../tests/unit/test_call_outcome_evidence.py) — `test_failed_release_capture_does_not_skip_release_verification`.
- [test_call_outcome_evidence.py](../../tests/unit/test_call_outcome_evidence.py) — `test_prepare_failure_does_not_capture_a_previous_calls_release`.
- [test_call_outcome_evidence.py](../../tests/unit/test_call_outcome_evidence.py) — `test_voicemail_is_model_evidence_and_cancels_worker_without_gate_end_frame`.
- [test_call_outcome_evidence.py](../../tests/unit/test_call_outcome_evidence.py) — `test_timeout_is_unknown_releases_gate_and_ignores_late_voicemail`.
- [test_call_outcome_evidence.py](../../tests/unit/test_call_outcome_evidence.py) — `test_human_detection_does_not_trigger_timeout_or_voicemail_hangup`.
- [test_call_outcome_evidence.py](../../tests/unit/test_call_outcome_evidence.py) — `test_unrelated_and_unknown_urcs_during_a_command_are_not_retained`.
- [test_call_outcome_evidence.py](../../tests/unit/test_call_outcome_evidence.py) — `test_failed_detection_releases_gate_without_failing_main_pipeline`.
- [test_call_outcome_evidence.py](../../tests/unit/test_call_outcome_evidence.py) — `test_voicemail_configuration_defaults_and_bounds`.

## Verification limits

Other-side attribution is an operational rule, not a carrier initiator identity. The serial trailing-terminator investigation below remains separate.

These links identify existing coverage. See [verification record](verification.md) for commands rerun during this review. Follow the [regression guide](../testing/regression-tests.md) before changing behavior.
