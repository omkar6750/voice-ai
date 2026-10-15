# ISSUE-002 Repeated tool notifications caused conflicting evidence

Status: Implemented. Reviewed October 15, 2026.

## Observed problem

A tool result reached context notification twice with different delivery metadata. Strict ingestion rejected conflicting immutable evidence; the model need not have called the tool twice.

## Implemented behavior

Deduplicate result context notification and flow side effects. Isolate the voicemail branch from conversation tool-control broadcasts. Keep API validation strict.

## Source

- [packages/voice_runtime/voice_runtime/execution/flow_manager.py](../../packages/voice_runtime/voice_runtime/execution/flow_manager.py)
- [packages/voice_runtime/voice_runtime/execution/exchange.py](../../packages/voice_runtime/voice_runtime/execution/exchange.py)
- [packages/voice_runtime/voice_runtime/execution/voicemail.py](../../packages/voice_runtime/voice_runtime/execution/voicemail.py)

## Regression coverage

- [test_native_evidence.py](../../tests/unit/test_native_evidence.py) — `test_repeated_context_notifications_keep_one_delivery_and_consumption`.
- [test_end_call_ordering.py](../../tests/unit/test_end_call_ordering.py) — `test_duplicate_context_notification_does_not_repeat_flow_side_effects`.
- [test_voicemail_context_isolation.py](../../tests/unit/test_voicemail_context_isolation.py) — `test_conversation_tool_result_cannot_update_voicemail_context`.
- [test_voicemail_context_isolation.py](../../tests/unit/test_voicemail_context_isolation.py) — `test_llm_evidence_records_one_tool_call_for_bidirectional_broadcast`.

## Verification limits

Do not turn a 409 into success or discard conflicting evidence to hide this error.

These links identify existing coverage. See [verification record](verification.md) for commands rerun during this review. Follow the [regression guide](../testing/regression-tests.md) before changing behavior.
