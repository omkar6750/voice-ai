# PLAN-0011 · Classifier entry and exit execution

Status: completed

The provider, tool-collapse, and context-budget work is tracked in PLAN-0019.

## Existing facts

- `classifier.node_entries` and `classifier.node_exits` exist in the contract but are not consumed by runtime code.
- Generic `entry_actions` and `exit_actions` are rejected by the native runtime.
- Classifier handlers exist, but recent evidence contains no classifier invocations.

## Scope

- Execute configured entry classifiers after node entry.
- Execute configured exit classifiers before node transition.
- Add classifier results to the next LLM context through Pipecat public APIs.

## Contracts

- Add typed classifier operation/result/context-delivery evidence.
- Preserve classifier phase, node, provider, model, transcript identity, result, and failure state.

## Runtime and frontend behavior

- Select LLM or JEV implementation from typed classifier configuration.
- Prevent duplicate execution.
- Fail open unless explicitly required.
- Show classifier spans and context delivery in the timeline.

## Implementation

- `TracedFlowManager._set_node` now runs configured exit classifiers for the
  node being left, then configured entry classifiers for the node being entered.
- Classifier execution is selected from the typed snapshot configuration:
  `classifier_type=llm` uses the configured Groq classifier model and
  `classifier_type=jev` uses the configured TypeSafe System One model/questions.
- Classifier execution is fail-open. Provider/configuration failures produce a
  failed classifier result and an internal context message, while node setup
  continues.
- Classifier results are appended to the following node's `NodeConfig.task_messages`
  using Pipecat's public flow/context update path. The message is marked with a
  stable runtime result ID so the observer can prove delivery and consumption.
- Added typed classifier result and context-delivery evidence, relational
  `classifier_results` and `classifier_context_deliveries` tables, timeline API
  fields, and dashboard rendering in classifier span details and the waterfall.
- Classifier spans are ordinary trace spans with `category=classifier`, while
  their result and context lifecycle are separately queryable.

## Tests and acceptance

- Unit coverage verifies classifier evidence delivery/consumption and configured
  node classifier execution.
- PostgreSQL integration coverage verifies classifier result persistence,
  delivery, and exact consuming LLM operation linkage.
- 25 focused tests passed; Ruff passed for all changed backend/runtime/migration
  and test files.
- OpenAPI export, dashboard type generation, and dashboard production build
  passed.

## Manual verification

- Configure entry and exit nodes.
- Run through both nodes.
- Inspect classifier span, result, context insertion, and consuming LLM span.

## Verification result

Completed on 2026-09-27. Migration `0018_classifier_evidence` is applied to the
development database. The generated API contract includes classifier result and
classifier context-delivery response types.

## Non-goals

- No changes to demo or seed scripts.

## Boundary

Plan 0011 is complete. Plan 0012 (waterfall, barge-in, and interruption
tracking) has not been started in this boundary.
