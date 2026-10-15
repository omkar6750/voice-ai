# ISSUE-004 Evidence failure hid release and left a modem occupied

Status: Implemented; recovery requires hardware proof. Reviewed October 15, 2026.

## Observed problem

A failed evidence batch or expired execution lease did not establish whether execution and transport were stopped. The UI could show an occupied endpoint although the modem appeared idle.

## Implemented behavior

Synchronize lifecycle cleanup independently of transcript batches. Keep unsaved evidence in the spool and incomplete flags explicit. Recovery verifies the previous owner and hardware before releasing the lease.

## Source

- [apps/runtime/voice_runner/session.py](../../apps/runtime/voice_runner/session.py)
- [apps/runtime/voice_runner/modem_recovery.py](../../apps/runtime/voice_runner/modem_recovery.py)
- [apps/api/voice_api/api/v1/endpoints/runtime.py](../../apps/api/voice_api/api/v1/endpoints/runtime.py)
- [packages/voice_shared/voice_shared/contracts.py](../../packages/voice_shared/voice_shared/contracts.py)

## Regression coverage

- [test_runtime_cleanup_sync.py](../../tests/unit/test_runtime_cleanup_sync.py) — `test_terminal_sync_updates_run_call_callback_and_lease`.
- [test_modem_recovery.py](../../tests/unit/test_modem_recovery.py) — `test_recovery_releases_stopped_owner_only_after_hardware_proof`.
- [test_modem_recovery.py](../../tests/unit/test_modem_recovery.py) — `test_active_modem_call_is_not_hung_up_or_released`.
- [test_modem_recovery.py](../../tests/unit/test_modem_recovery.py) — `test_status_contract_keeps_historical_records_and_rejects_malformed_runtime_status`.

## Verification limits

Lease expiry alone is not a physical disconnect. Runtime/API contract mismatch is a service problem, not an operator input error.

These links identify existing coverage. See [verification record](verification.md) for commands rerun during this review. Follow the [regression guide](../testing/regression-tests.md) before changing behavior.
