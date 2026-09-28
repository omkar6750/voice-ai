# ADR-0011 · Classifier entry/exit execution and context evidence

Status: Accepted  
Date: 2026-09-27  
Related: [PLAN-0011](../plan/PLAN-0011-classifier-entry-exit-execution.md), [ADR-0007](ADR-0007-exchanges-and-integration-secrets.md), [ADR-0010](ADR-0010-tool-context-delivery-evidence.md)

## Context

Agent configuration already exposed `classifier.node_entries` and
`classifier.node_exits`, and the dashboard allowed operators to select node
checkpoints. The live native runtime never consumed those fields. It rejected
generic `entry_actions` and `exit_actions`, but did not distinguish those
unsupported generic actions from the supported classifier configuration. As a
result, configured classifiers did not run and their results could not appear
in the next LLM request.

The old demo executed Jev as an out-of-band background task during a transition.
That did not make the result part of the following Pipecat context and did not
produce durable classifier evidence. The configurable runtime needs a
deterministic node lifecycle hook instead.

## Decision

The classifier contract and delivery details are extended by ADR-0019: the
active runtime exposes only `classify_lead`, and automatic/dynamic execution
shares the agent-selected JEV or Pipecat LLM backend.

Use the installed Pipecat 1.11.0 `FlowManager._set_node` lifecycle as the single
runtime hook:

1. When leaving an existing node, run its configured exit classifier.
2. Run the target node's configured entry classifier.
3. Append both results, in that order, to the target `NodeConfig.task_messages`.
4. Let Pipecat's normal node context update and `LLMRunFrame` path deliver those
   messages to the next LLM request.

The runtime does not mutate Pipecat private context internals and does not use a
background task for automatic classifiers. A classifier failure is recorded and
the node transition continues (fail-open); no classifier failure silently
disables evidence.

Generic `entry_actions` and `exit_actions` remain unsupported. They are a
separate contract from the typed classifier checkpoint fields.

## Provider selection

- `classifier_type=llm` uses the configured classifier LLM provider/model. The
  current implementation supports the runtime's Groq classifier adapter and
  records an explicit failed result for another provider rather than silently
  using the wrong key or model.
- `classifier_type=jev` uses the configured TypeSafe System One endpoint, model,
  and question map.
- Provider failures, missing keys, unsupported providers, and malformed runtime
  execution produce a failed classifier result and an internal context message.

## Evidence and data flow

```text
FlowManager._set_node
  -> classifier operation_started (category=classifier)
  -> provider classifier call
  -> classifier span (completed/failed)
  -> classifier_result record
  -> NodeConfig.task_messages internal developer message
  -> Pipecat context update
  -> observer sees marker in LLMContextFrame
  -> classifier_context_updated
  -> classifier_result_consumed linked to exact LLM operation
```

Classifier spans use the existing typed operation/span protocol with
`category=classifier`. Dedicated typed records make result and context state
queryable without pretending the automatic checkpoint was an LLM tool
invocation:

- `ClassifierResultRecorded` preserves phase, node, classifier type, result,
  failure state, and a SHA-256 identity of the transcript supplied to the
  provider.
- `ClassifierContextUpdated` proves the result marker was present in the actual
  LLM context and records its message index.
- `ClassifierResultConsumed` links delivery to the exact consuming LLM span.

The database mirrors this protocol in `classifier_results` and
`classifier_context_deliveries`. The run timeline returns both collections.

## UI behavior

Classifier operations appear as `classifier` spans in the existing waterfall.
The waterfall shows phase, result state, and context state. Selecting the span
shows the structured classifier result, failure, delivery timestamp, context
state, and consuming operation ID.

## API and migration changes

- Evidence union now accepts the three classifier-specific records.
- Timeline response schemas expose classifier results and context deliveries.
- Migration `0018_classifier_evidence` creates the two append-oriented evidence
  tables with ownership, uniqueness, phase/type/status, and message-index
  constraints.
- OpenAPI remains the source of generated dashboard types.

## Verification

- Migration applied successfully to PostgreSQL.
- Focused unit/integration suite: 25 passed, with only the two existing Pipecat
  deprecation warnings.
- Ruff passed for changed backend, runtime, migration, and test files.
- OpenAPI export passed.
- Dashboard generated types and production build passed.
- No demo or seed scripts were modified.

## Known limitations

- A live provider-backed call was not run during this implementation; manual
  verification must exercise both configured classifier types.
- The current LLM classifier adapter is Groq-specific. Other typed LLM provider
  support belongs to the model/provider configuration work, and unsupported
  choices are visible as failed classifier evidence.
- Generic configured entry/exit actions remain unsupported by design.
