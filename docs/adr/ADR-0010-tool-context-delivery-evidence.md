# ADR-0010 · Tool-result context delivery and consumption evidence

Status: Accepted  
Date: 2026-09-27  
Related: [PLAN-0010](../plan/PLAN-0010-tool-context-delivery.md), [ADR-0007](ADR-0007-exchanges-and-integration-secrets.md)

## Context

The runtime already used Pipecat's standard `FunctionCallParams.result_callback`
path. That path is responsible for delivering a function result to the
`LLMContextAggregatorPair`, but the evidence model only represented the result
and an inferred later consumption. The dashboard therefore could not prove that
a result was inserted into context, distinguish delivery from consumption, or
link consumption to the exact LLM operation.

The native host also wraps Pipecat FlowManager callbacks. Replacing
`FunctionCallResultProperties.on_context_updated` would risk breaking FlowManager
transitions, so observability must compose the callback rather than own it.

## Decision

Keep Pipecat's standard callback strategy. Do not mutate private context message
state or inject manual `LLMContextFrame` objects for ordinary function results.
Instead:

1. The runtime invokes the registered function through Pipecat.
2. The wrapped result callback composes the existing `on_context_updated`
   callback with an evidence callback.
3. The evidence callback records `tool_result_context_updated` only after
   Pipecat reports that the context update completed.
4. The next LLM operation calls `consume_results` and links each pending result
   to that operation.

Delivery and consumption are separate facts. A result can be delivered without
being consumed if the call is interrupted or ends before another LLM request.
Intermediate and final results each receive their own delivery row.

## Data model and contracts

`tool_context_deliveries` is the canonical relational record for this evidence:

- `tool_invocation_id` and `result_id` identify the source result;
- `function_call_id` preserves provider/function-call correlation;
- `is_final` distinguishes intermediate from final result delivery;
- `status` is `delivered`, `consumed`, `context_update_failed`, or
  `interrupted_before_consumption`;
- `context_message_index` records the observed message index without mutating
  Pipecat internals;
- `consuming_exchange_id` and `consuming_span_id` identify the LLM operation
  that consumed the result.

The public timeline API now returns typed `ToolContextDeliveryResponse` records.
The evidence ingestion API accepts the typed context-update record and optional
`consuming_operation_id` on consumption records. Existing result and consumption
records remain accepted for historical/backward-compatible evidence.

## Runtime behavior

`ExchangeEvidenceTracker.context_updated()` emits the delivery evidence and only
then makes that result eligible for consumption. The observer starts the LLM
operation before consuming pending results, allowing the consumption record to
refer to the exact operation. The native host composes the original FlowManager
callback after emitting delivery evidence.

## UI behavior

The run inspector, transcript, and waterfall display:

- whether a result was added to context;
- delivery status;
- observed context message index; and
- the consuming LLM span when available.

Historical runs without delivery rows retain the previous exchange-based
consumption fallback so the UI remains useful during the development migration.

## Verification

- Migration `0017_tool_context_delivery` applied successfully.
- Focused unit and integration suite: 22 passed, 2 existing Pipecat deprecation
  warnings.
- Ruff passed for changed backend, runtime, migration, and test files.
- OpenAPI export passed.
- Dashboard generated types and production build passed.
- `git diff --check` passed; only expected line-ending warnings were reported by
  Git for the Windows working tree.

## Known limitations

- Historical evidence without a delivery record cannot be retroactively proven
  to have updated context; it continues to use the legacy display fallback.
- `context_message_index` is an observed index at callback time, not a durable
  Pipecat message identifier.
- A future failure-specific callback can persist `context_update_failed` and
  `interrupted_before_consumption` more explicitly; this change establishes the
  statuses and normal delivered/consumed path first.
