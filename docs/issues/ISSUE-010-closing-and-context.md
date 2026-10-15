# ISSUE-010 Terminal actions and context changes caused extra speech or failures

Status: Implemented mechanics; prompt quality remains separate. Reviewed October 15, 2026.

## Observed problem

Terminal responses could request another inference, race result delivery, or overwrite an earlier disconnect/failure. Node changes could lose history or leave invalid tool/result pairs.

## Implemented behavior

Deliver end-call tool results before queuing one shutdown frame, suppress its follow-up inference and preserve earlier causes. Record terminal entry only after setup. Keep append/reset and summary compaction semantics explicit.

## Source

- [packages/voice_runtime/voice_runtime/execution/flow_manager.py](../../packages/voice_runtime/voice_runtime/execution/flow_manager.py)
- [packages/voice_runtime/voice_runtime/execution/termination.py](../../packages/voice_runtime/voice_runtime/execution/termination.py)
- [packages/voice_runtime/voice_runtime/execution/context.py](../../packages/voice_runtime/voice_runtime/execution/context.py)

## Regression coverage

- [test_end_call_ordering.py](../../tests/unit/test_end_call_ordering.py) — `test_end_call_delivers_result_before_end_without_followup_inference`.
- [test_end_call_ordering.py](../../tests/unit/test_end_call_ordering.py) — `test_repeated_end_call_records_results_but_queues_one_end_frame`.
- [test_terminal_node_shutdown.py](../../tests/unit/test_terminal_node_shutdown.py) — `test_terminal_action_cannot_overwrite_prior_disconnect_or_error`.
- [test_terminal_node_shutdown.py](../../tests/unit/test_terminal_node_shutdown.py) — `test_duplicate_terminal_completion_queues_end_once`.
- [test_context_history.py](../../tests/unit/test_context_history.py) — `test_compaction_never_orphans_tool_results`.

## Verification limits

Respond-on-entry and prompt instructions still govern conversational flow. A terminal entry is not proof the full farewell played.

These links identify existing coverage. See [verification record](verification.md) for commands rerun during this review. Follow the [regression guide](../testing/regression-tests.md) before changing behavior.
