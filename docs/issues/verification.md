# Verification record

Date: October 15, 2026. Baseline: `42f7b10`. The work in this review changes
documentation and removes explicitly requested Tessl tooling. Application modules,
test expectations, agent configurations and databases were not changed.

## Regression tests rerun

The focused command selected these existing unit suites:

```powershell
uv run pytest -p no:cacheprovider --basetemp=data/docs-audit-20261015/pytest tests/unit/test_sim7600_release_verification.py tests/unit/test_end_call_ordering.py tests/unit/test_native_evidence.py tests/unit/test_voicemail_context_isolation.py tests/unit/test_voicemail_tts_gate.py tests/unit/test_runtime_cleanup_sync.py tests/unit/test_run_stop.py tests/unit/test_initial_task_message.py tests/unit/test_provider_failover.py tests/unit/test_sarvam_llm.py tests/unit/test_whatsapp_composer.py tests/unit/test_flat_contact_variables.py tests/unit/test_referral_contracts.py tests/unit/test_speech_service_construction.py tests/unit/test_modem_recovery.py tests/unit/test_terminal_node_shutdown.py tests/unit/test_terminal_visit_completion.py tests/unit/test_context_history.py tests/unit/test_context_reset_semantics.py tests/unit/test_call_outcome_evidence.py
```

Result: **170 passed, 2 failed**, with three dependency/deprecation warnings.
Both failures reproduced in a separate invocation selecting only their test IDs:

- `test_provider_failover.py::test_groq_fallback_preserves_current_node_instruction_and_user_task`
- `test_terminal_node_shutdown.py::test_terminal_queue_failure_keeps_failure_cause_with_completed_terminal_outcome`

[OPEN-005](open-investigations.md#open-005-existing-test-expectations-conflict-with-current-policies)
explains the observed expectation mismatches. The suite is not fully green. This
review did not change tests merely to remove failures or claim a new runtime fix.

## Static and documentation checks

- `uv run ruff check .` passed.
- Every test function named by the generated incident catalog was checked against
  the parsed source inventory before its link was written.
- The ADR/RFC inventory covered 46 existing ADRs and 14 RFCs. Three retrospective
  ADRs were added; no RFC was created or promoted from Proposed to Accepted.
- The issue change-history index lists 131 non-merge commits reachable from the
  reviewed baseline. Commit subjects are historical records, not acceptance results.
- All local Markdown links in the documentation/root guides resolve. `git diff --check`
  passed. Audits and intermediate renders remain ignored under `data/`.

## Not performed

No live call, provider request, WhatsApp send, booking, Clerk role change, production
import, storage upload, migration, deployment or broad compatibility removal ran.
Database integration and dashboard suites were not rerun because application/UI
behavior did not change. The unused-module candidates remain in source.
