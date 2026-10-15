# ISSUE-007 Providers rejected missing initial user input and cloning failed

Status: Implemented. Reviewed October 15, 2026.

## Observed problem

An immediately responding initial node could send a system-only or empty messages request. Enforcing the new requirement also initially blocked cloning old published configurations for repair.

## Implemented behavior

Require a nonempty initial user task for responding nodes. Permit legacy reads and cloning into an editable draft; enforce current rules on new saves/publication. Do not inject a hidden hard-coded user query.

## Source

- [packages/voice_runtime/voice_runtime/contracts/agent.py](../../packages/voice_runtime/voice_runtime/contracts/agent.py)
- [apps/api/voice_api/services/publication_service.py](../../apps/api/voice_api/services/publication_service.py)

## Regression coverage

- [test_initial_task_message.py](../../tests/unit/test_initial_task_message.py) — `test_initial_response_requires_nonempty_user_task`.
- [test_initial_task_message.py](../../tests/unit/test_initial_task_message.py) — `test_legacy_version_readable_but_write_rejected`.
- [test_initial_task_message.py](../../tests/unit/test_initial_task_message.py) — `test_clone_published_version_without_opening_task_preserves_draft`.

## Verification limits

A verbatim opening with a waiting initial node follows a different path.

These links identify existing coverage. See [verification record](verification.md) for commands rerun during this review. Follow the [regression guide](../testing/regression-tests.md) before changing behavior.
