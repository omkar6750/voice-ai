# ISSUE-001 Dashboard stop became a pipeline failure

Status: Implemented; hardware acceptance remains separate. Reviewed October 15, 2026.

## Observed problem

Ending a modem call from the dashboard closed modem audio while queued playback writes were still running. The resulting PCM write error obscured the operator stop.

## Implemented behavior

Stop and await the pipeline before hangup/audio disable. A failed pipeline stop still attempts physical cleanup. The stop API fences preparation and keeps ownership until release is confirmed.

## Source

- [packages/voice_runtime/voice_runtime/telephony/driver.py](../../packages/voice_runtime/voice_runtime/telephony/driver.py)
- [apps/api/voice_api/api/v1/endpoints/runs.py](../../apps/api/voice_api/api/v1/endpoints/runs.py)
- [apps/dashboard/src/pages/runs/end-call-button.tsx](../../apps/dashboard/src/pages/runs/end-call-button.tsx)

## Regression coverage

- [test_sim7600_release_verification.py](../../tests/unit/test_sim7600_release_verification.py) — `test_pipeline_stops_before_hangup_disables_pcm`.
- [test_sim7600_release_verification.py](../../tests/unit/test_sim7600_release_verification.py) — `test_failed_pipeline_shutdown_still_hangs_up_and_closes_modem`.
- [test_run_stop.py](../../tests/unit/test_run_stop.py) — `test_queued_stop_cancels_before_dispatch`.
- [test_run_stop.py](../../tests/unit/test_run_stop.py) — `test_terminal_stop_is_idempotent`.
- [test_run_stop.py](../../tests/unit/test_run_stop.py) — `test_missing_owner_does_not_invent_transport_release`.

## Verification limits

Historical failure labels are not rewritten. A fake modem proves ordering, not carrier behavior.

These links identify existing coverage. See [verification record](verification.md) for commands rerun during this review. Follow the [regression guide](../testing/regression-tests.md) before changing behavior.
