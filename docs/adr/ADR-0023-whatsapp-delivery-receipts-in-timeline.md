# ADR-0023 · WhatsApp delivery receipts in run timelines

Status: Accepted
Date: 2026-09-28
Related: [ADR-0010](ADR-0010-tool-context-delivery-evidence.md),
[ADR-0014](ADR-0014-tool-and-whatsapp-authoring.md),
[PLAN-0010](../plan/PLAN-0010-tool-context-delivery.md)

## Context

Meta's outbound `/messages` response means the provider accepted a send request;
it does not establish that the recipient received or read the message. WhatsApp
webhooks can later report `sent`, `delivered`, `read`, or `failed`. The endpoint
already verified signatures, correlated status notifications to
`ToolInvocation.provider_message_id` plus the integration connection, and
stored de-duplicated receipt payloads. However, the run timeline omitted those
stored receipts, so the waterfall and transcript could not distinguish send
acceptance from delivery outcome.

## Decision

Expose a typed, sanitized receipt projection on each timeline tool invocation:
status, provider timestamp, recipient ID, and provider error details. Render the
latest status and the full ordered receipt history in waterfall, transcript,
and tool inspector. `sent` means WhatsApp sent the message but does not imply
recipient delivery; `delivered` and `read` remain distinct; `failed` displays
available provider error details. A send failure before a provider message ID
is recorded is distinguished from a later delivery failure.

When a provider message ID exists but no receipt has arrived, show delivery as
unconfirmed/unavailable (or waiting while the run is still active). Absence of a
receipt is not reported as delivery failure. Refreshing/reloading an active run
fetches any webhook receipts that have since arrived; completed runs can be
manually refreshed to pick up a later callback.

Webhook receipts are observability evidence only in this change. They do not
become a second tool result, alter Pipecat context, or cause an automatic spoken
confirmation. A future acknowledge-and-continue design is deferred until its
asynchronous job lifecycle, context re-entry, interruption, and hangup semantics
are specified.

## Tool guidance and wait controls

Native flow construction passes the saved tool description and each input
property's schema description into Pipecat `FlowsFunctionSchema`. These are the
tool-specific instructions available to the composer/model; agent-wide
instructions remain in the role/system and node prompts. A regression test
checks that descriptions survive construction.

The `continue_conversation` wait value is removed because there is no async
result/context re-entry lifecycle. The current runtime does not execute
acknowledgement settings, so the dashboard no longer offers wait controls and
generated configs default to `silent_wait`. Existing `acknowledge_then_wait`
values remain accepted while old versions are audited; runtime still awaits
normal tool execution and does not claim to speak the configured acknowledgement.

## Verification

- Added integration coverage for account-scoped, de-duplicated webhook
  receipts appearing in the timeline with failure details. It is opt-in and was
  skipped in this workspace because `VOICE_TEST_DATABASE_URL` is not configured.
- Dashboard TypeScript generation and build/typecheck cover the typed UI
  projection and the waterfall/transcript/inspector states.
- No live WhatsApp webhook subscription or send is required by automated tests.
