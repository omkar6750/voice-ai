---
id: ADR-0026
title: Nonblocking lead classification with caller-turn context delivery
status: Accepted
version: 1
date: 2026-09-29
related: [ADR-0007, ADR-0021, ADR-0023, ADR-0025]
---

Only the callable `classify_lead` tool runs asynchronously. Its invocation first
records a running operation, returns a `started` result through Pipecat's normal
function-result callback, and continues classification in a supervised task.
Entry/exit classifiers, WhatsApp sends, knowledge retrieval, callback tools, and
flow-control tools remain awaited. Generic HTTP tools remain unsupported.

The final classifier outcome and WhatsApp delivery receipts use the new
run-scoped `run_context_events` inbox. Events are idempotent by `(run_id,
dedupe_key)`, bounded and sanitized before model visibility, and have explicit
`pending`, `delivered`, `consumed`, or `ended_before_delivery` lifecycle states.
The timeline response enforces these status and source values with Pydantic
`Literal` types and matching database constraints. WhatsApp receipt events use
the provider's timestamp for event ordering and remain distinct from the
original Meta send acceptance and the assistant transcript.

Pipecat 1.11.0 source inspection showed `on_user_turn_inference_triggered` fires
after the user aggregator has pushed its `LLMContextFrame`. Therefore delivery
does not happen in that event callback. A provider-neutral processor immediately
before the LLM observes the frame, identifies a new caller message, appends
pending events to that same context, and only then forwards the frame. It does
not drain events for a tool-result inference with no new caller message. The
observer marks an event consumed only after the LLM receives a context frame
containing its marker.

The FlowManager wrapper preserves the prompt-time `started` classifier result
instead of normalizing it as a final classifier label. Final results are
normalized and stripped of internal diagnostics before being enqueued. Tool
result callback recording remains standard Pipecat `result_callback` behavior;
the durable inbox is used for outcomes that arrive after that callback has
settled.

The run inspector, waterfall, and transcript display event payload, source,
timestamps, context delivery, LLM consumption, and ended-before-delivery state.
Actual spoken text continues to come only from assistant transcript evidence.

Verification: the full unit suite passes; Ruff passes; OpenAPI export, dashboard
type generation, and production build pass. Revisions `0027→0028` and `0028→0029`
both render successfully in targeted PostgreSQL offline SQL mode. Eleven
database-backed integration tests were skipped because the integration database
is not configured; neither migration was applied here. Rendering the entire
historical chain offline remains blocked by migration `0003`, which requires
live schema inspection. A live WhatsApp webhook-to-next-caller-turn test
requires a public configured Meta webhook and remains manual.
