# ISSUE-011 Contact variables were inconsistent and referral facts had no review lifecycle

Status: Implemented. Reviewed October 15, 2026.

## Observed problem

Full-name and nested contact aliases were inconsistent across prompt editors and runtime paths. Referral details saved as scattered conversation facts did not provide independent review or source provenance.

## Implemented behavior

Use flat first_name/last_name variables and normalize historical aliases on copies. Capture referrals as independent tenant-owned records; optional details remain valid and operator verification/promotion is explicit.

## Source

- [packages/voice_runtime/voice_runtime/contracts/agent.py](../../packages/voice_runtime/voice_runtime/contracts/agent.py)
- [apps/api/voice_api/services/referral_service.py](../../apps/api/voice_api/services/referral_service.py)
- [apps/api/voice_api/models/referrals.py](../../apps/api/voice_api/models/referrals.py)

## Regression coverage

- [test_flat_contact_variables.py](../../tests/unit/test_flat_contact_variables.py) — `test_config_translation_preserves_original_and_deduplicates_variables`.
- [test_referral_contracts.py](../../tests/unit/test_referral_contracts.py) — `test_referral_never_guesses_phone_country_and_trims_unknown_fields`.

## Verification limits

Integration coverage for promotion, same-org references and survival after cleanup lives in tests/integration/test_referrals.py and needs an isolated database.

These links identify existing coverage. See [verification record](verification.md) for commands rerun during this review. Follow the [regression guide](../testing/regression-tests.md) before changing behavior.
