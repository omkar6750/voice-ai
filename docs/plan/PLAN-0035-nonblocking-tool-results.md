# PLAN-0035 — Nonblocking classifier result and durable context events

Status: Completed (2026-09-29; live database/webhook verification pending)

## Existing facts

- `TracedFlowManager` awaits the registered handler and routes the result through Pipecat's standard result callback.
- Entry/exit node classifiers are awaited and their result is compiled into the node prompt. Only the callable `classify_lead` is nonblocking.
- WhatsApp sends and knowledge retrieval remain awaited. WhatsApp delivery webhooks arrive later, are correlated with the outbound message, and can be queued as separate context events.
- The configured Pipecat version is 1.11.0. In that version the user aggregator's `on_user_turn_inference_triggered` event is emitted after `push_aggregation()` has already pushed an `LLMContextFrame`; it is too late to add context for that inference.
- Generic HTTP tools are not used in calls and remain unsupported. This plan does not add HTTP-tool execution.

## Scope and runtime behavior

- Run only callable `classify_lead` in a supervised background task. Persist its started operation through the existing evidence tracker before dispatch, return `started` immediately, and do not retry automatically after uncertainty. Every other handler, including WhatsApp and knowledge retrieval, stays awaited.
- Persist bounded, sanitized classifier outcomes and WhatsApp webhook receipts in `run_context_events`, with run-scoped deduplication and provider timestamps for receipt ordering. Keep tool invocation receipt history as the authoritative outbound-message correlation record.
- Add model-visible outcomes only when a new caller message is present on an `LLMContextFrame`, in a provider-neutral processor immediately before the LLM. Never drain on a tool-result inference, mutate an inference after it entered the LLM, or trigger unsolicited speech.
- Track `pending → delivered → consumed` separately; calls that end first become `ended_before_delivery`. An outcome delivered to context is marked consumed only when the observer sees its event marker in the actual LLM context frame.
- A WhatsApp send result means only that Meta accepted/rejected the send. A later webhook receipt (`sent`, `delivered`, `read`, `failed`) is a separate event. No receipt means delivery remains unconfirmed, not failed. The receipt may be discussed only after a later caller-driven turn.
- Preserve actual assistant speech as the transcript source. Do not synthesize a fixed acknowledgement.
- Surface context-event payload, timestamps, delivery, consumption, and terminal status separately in the run timeline, waterfall, and transcript.

## Contracts, files, and data

- Runtime: `packages/voice_runtime/voice_runtime/execution/native.py`, `flow_manager.py`, and `observer.py`.
- API/database: `RunContextEvent`, Alembic revision `0028_run_context_events`, idempotent `run_context_service`, WhatsApp webhook ingestion, and typed timeline response.
- Dashboard: run inspector, waterfall, and transcript projections.
- OpenAPI and generated dashboard API types follow the repository generation flow.

## Tests and acceptance

- A unit regression verifies classifier dispatch returns `started` without awaiting work; the handler policy test verifies all tools other than `classify_lead` remain awaited.
- A processor regression verifies queued outcomes are added before the LLM receives a caller-turn context frame and are not drained on a repeated/tool-result frame without a new caller message.
- Unit and integration tests cover bounded result payloads, event deduplication, webhook receipt status/timestamps, ended-run handling, and timeline lifecycle projection.
- Validate the migration, Python tests, Ruff, OpenAPI export, dashboard type generation/typecheck/build, and applicable database integration tests.

## Non-goals

- No nonblocking WhatsApp send, knowledge retrieval, generic HTTP, or classifier entry/exit execution.
- No callback availability/booking changes; those remain awaited under PLAN-0034.
- No fixed acknowledgement, proactive speech, automatic duplicate external sends, or provider-usage reporting.
- No changes to demo/seed scripts.

## Verification

- Pipecat 1.11.0 source inspection confirmed the aggregator event fires after its context frame push; result injection was moved to the pre-LLM frame processor.
- Full unit suite, Ruff, OpenAPI export, dashboard type generation, and production build pass. Eleven database integration tests skip without a configured integration database.
- Revisions `0027→0028` and `0028→0029` render successfully in targeted PostgreSQL offline SQL mode. Eleven database integration tests skip without the isolated DB; migrations were not applied. Rendering the full historical chain offline is blocked by migration `0003_integrity_and_run_ownership`, which requires live schema inspection.
- Live WhatsApp webhook/context delivery requires a configured public webhook URL and a subsequent caller turn.
