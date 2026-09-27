# PLAN-0010 · Tool result context delivery evidence

Status: completed

## Existing facts

- Pipecat `result_callback` already adds ordinary tool results to context.
- Later inference evidence contains `role: "tool"` messages.
- The timeline currently shows tool invocation, result, and LLM spans separately.

## Scope

- Distinguish result delivery from result consumption.
- Compose, rather than overwrite, Pipecat `on_context_updated` callbacks.
- Persist typed context-delivery evidence.

## Contracts

- Add `ToolContextDelivery` with invocation/result/tool-call IDs, delivery state, context index, consuming span, and timestamps.
- Expose typed delivery records in the run timeline response.

## Runtime and frontend behavior

- `delivered` means the result updated context.
- `consumed` means a later LLM input actually contained it.
- Intermediate and final results are tracked independently.

## Implementation

- Added the `tool_context_deliveries` table and `ToolContextDelivery` ORM model.
- Added typed `tool_result_context_updated` evidence and enriched
  `tool_result_consumed` evidence with invocation, function-call, and consuming
  operation identity.
- Composed Pipecat `FunctionCallResultProperties.on_context_updated` in the
  native host so FlowManager callbacks remain intact while delivery evidence is
  recorded after Pipecat updates the context.
- Linked result consumption to the LLM operation that received the result.
- Added typed timeline response schemas and exposed delivery rows from the run
  timeline endpoint.
- Updated the inspector, transcript, and waterfall to show delivery status,
  context message index, and the exact consuming LLM span when available.
- Preserved the legacy exchange-based fallback for historical evidence that has
  no delivery row.

## Tests and acceptance

- Focused unit and integration coverage verifies normal result delivery,
  consumption linked to the consuming LLM span, and existing evidence behavior.
- PostgreSQL migration and timeline serialization were exercised against the
  development database.
- Existing FlowManager callback composition remains covered by the native
  evidence tests.
- 22 focused tests passed; Ruff passed for all changed backend/runtime/migration
  and test files.
- OpenAPI export, dashboard type generation, and dashboard production build
  passed.

## Manual verification

- Trigger a tool.
- Inspect the timeline for “Added to context” and “Consumed by LLM”.
- Confirm intermediate and final results have separate delivery records.

## Verification result

Completed on 2026-09-27. The local database is at migration `0017` and the
generated API contract includes `ToolContextDeliveryResponse`.

## Non-goals

- No manual mutation of private `LLMContext.messages`.
- No replacement of Pipecat's standard callback mechanism.

## Boundary

Plan 0010 is complete. Plan 0011 (classifier entry/exit execution) has not been
started in this boundary.
