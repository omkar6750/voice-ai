# ISSUE-005 Dial acceptance and a single idle reading were insufficient

Status: Implemented. Reviewed October 15, 2026.

## Observed problem

Some calls remained dialing beyond the old wait. A transient empty call list immediately after hangup could incorrectly appear to prove release.

## Implemented behavior

Wait for an active call before starting PCM/greeting. Use a configurable connect deadline and a stable idle interval inside a bounded release deadline; late active calls trigger another bounded hangup attempt.

## Source

- [packages/voice_runtime/voice_runtime/telephony/driver.py](../../packages/voice_runtime/voice_runtime/telephony/driver.py)
- [apps/runtime/voice_runner/settings.py](../../apps/runtime/voice_runner/settings.py)

## Regression coverage

- [test_sim7600_release_verification.py](../../tests/unit/test_sim7600_release_verification.py) — `test_late_call_is_hung_up_again_before_stable_release`.
- [test_sim7600_release_verification.py](../../tests/unit/test_sim7600_release_verification.py) — `test_persistent_call_is_uncertain_despite_successful_hangup_command`.
- [test_sim7600_release_verification.py](../../tests/unit/test_sim7600_release_verification.py) — `test_call_connection_timeout_has_last_state_and_does_not_start_audio`.

## Verification limits

A successful AT command is not proof of an answered call or released hardware.

These links identify existing coverage. See [verification record](verification.md) for commands rerun during this review. Follow the [regression guide](../testing/regression-tests.md) before changing behavior.
