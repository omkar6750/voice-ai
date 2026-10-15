---
id: ADR-0061
title: Isolate voicemail context and invalidate held speech
status: Accepted
version: 1
date: 2026-10-15
authored_by: codex
session: documentation-review-20261015
supersedes: null
superseded_by: null
related: [ADR-0010, ADR-0012, ADR-0059]
---

# Context

This retrospectively records fixes already implemented in `42f7b10`, extending
ADR-0059's phone-only voicemail decision. No new detector, model or policy is added.

The detector's parallel assistant aggregator could observe main conversation tool
broadcasts and invoke a result context callback twice. Its TTS gate also held frames
outside normal processor queues, allowing old speech to survive interruption.

# Decision

Keep conversation context/tool-control frames out of the voicemail branches in both
directions. Caller transcripts and synchronized lifecycle frames still fan out.
Record the model's downstream tool-start broadcast once. Independently make context
notification idempotent per result so duplicate framework callbacks cannot create a
second immutable delivery timestamp or repeat a node transition.

Invalidate held audio, text and speech-boundary frames on interruption or shutdown.
Fence in-progress gate release with an epoch and reject late output associated with
canceled TTS context IDs. New response frames preserve their order and remain usable.

# Evidence

- [Voicemail adapter](../../packages/voice_runtime/voice_runtime/execution/voicemail.py).
- [Context-isolation tests](../../tests/unit/test_voicemail_context_isolation.py).
- [Gate-race tests](../../tests/unit/test_voicemail_tts_gate.py).
- [Idempotent context evidence](../../tests/unit/test_native_evidence.py).
- [ISSUE-002](../issues/ISSUE-002-duplicate-tool-context.md) and
  [ISSUE-003](../issues/ISSUE-003-stale-greeting.md).

# Consequences

The adapter is a narrow Pipecat compatibility seam and must be reviewed on dependency
upgrades. Late context-free output still relies on the provider's cancellation.
This does not solve Sarvam word alignment or prove the exact words a caller heard.
The detector remains bounded and fail-open as described by ADR-0059.
