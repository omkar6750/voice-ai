# ISSUE-008 Fallback changed role handling or lost current node instructions

Status: Implemented. Reviewed October 15, 2026.

## Observed problem

Fallback requests could reject developer-role messages or omit the current node instruction/task. Retrying after partial output would duplicate caller-visible content or tool fragments.

## Implemented behavior

Use the provider service/context conversion for both primary and fallback. Preserve current node instructions and user task; bound retries and disallow fallback after visible text or tool fragments.

## Source

- [packages/voice_runtime/voice_runtime/execution/llm_factory.py](../../packages/voice_runtime/voice_runtime/execution/llm_factory.py)

## Regression coverage

- [test_provider_failover.py](../../tests/unit/test_provider_failover.py) — `test_groq_fallback_preserves_current_node_instruction_and_user_task`.
- [test_provider_failover.py](../../tests/unit/test_provider_failover.py) — `test_failure_after_text_or_tool_fragment_never_activates_fallback`.
- [test_sarvam_llm.py](../../tests/unit/test_sarvam_llm.py) — `test_groq_converts_developer_messages_for_primary_and_fallback`.
- [test_sarvam_llm.py](../../tests/unit/test_sarvam_llm.py) — `test_fallback_provider_error_cycles_once_to_primary`.

## Verification limits

Latency and rate-limit incidents require their actual request evidence; these tests do not establish an account quota or latency target.

These links identify existing coverage. See [verification record](verification.md) for commands rerun during this review. Follow the [regression guide](../testing/regression-tests.md) before changing behavior.
