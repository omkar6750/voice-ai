---
id: PLAN-0023
title: Call completion and controlled node actions
status: Proposed
date: 2026-09-27
related: [PLAN-0020, ADR-0011]
---

# Call completion and controlled node actions

## Why actions do not work now

The schema admits `entry_actions`/`exit_actions`, but `NativePipelineHost.prepare` explicitly rejects them and `background_hooks`; ADR-0011 kept generic actions unsupported while implementing a separate classifier checkpoint. This is a deliberate unsupported boundary, not missing Pipecat functionality. The `end_call` handler now queues an `EndFrame` instead of cancelling immediately, and the SIM7600 driver calls modem hangup after the pipeline returns. Focused tests cover idempotent frame queueing, modem hangup and cleanup failure, but they do not prove the last audio sample has played over carrier. Do not treat adding a built-in Flows action to saved config as a working fix until the runtime permits and wires it.

## Implementation sequence

1. Specify two end intents: caller explicitly requests immediate stop (hang up promptly), and normal agent close (finish speech/playback, then terminate). Expose `end_call` in every relevant node or a carefully reviewed global function, while keeping terminal-node behavior unambiguous.
2. Map Pipecat Flows pre/post action lifecycle onto the native host. Start with a small allow-list of built-ins (`tts_say` and `end_conversation`) and a typed action config; do not make arbitrary DB-bound tools runnable as entry/exit actions. Explicitly define whether current `entry_actions` and `exit_actions` map to Pipecat pre/post actions or rename them in a versioned contract. Reject unsupported legacy definitions with actionable publish errors, not only call-start failures.
3. For a normal close, mark close requested, prevent fresh inference/tool calls, wait for TTS and transport playback completion, then send bounded end frame/hangup with a timeout fallback. Record generated, synthesized, played, interrupted, and hung-up states separately. For immediate caller hangup, cancel quickly and skip any unsent farewell.
4. Make terminal completion and `end_call` idempotent. Ensure disconnect/error/timeout paths converge on one cleanup, no duplicate WhatsApp send, no double modem hangup, and no indefinite wait if TTS/playback never completes.
5. Add dashboard authoring affordances only for actions the live runtime supports, with clear timing labels (“before node response,” “after response playback”) and argument previews.

## Tests and acceptance

- Unit tests for normal close ordering, barge-in during goodbye, no playback completion, caller immediate stop, duplicate end request, pipeline failure, and unsupported action rejection.
- Browser transport and SIM7600 manual checks assert last spoken audio finishes before normal hangup, while caller hangup is prompt. Evidence must show whether audio actually played.
- Do not implement generic arbitrary actions or alter classifier lifecycle in this slice.

Refs: [Pipecat Flows actions](https://docs.pipecat.ai/pipecat/flows/actions), [pipeline termination](https://docs.pipecat.ai/pipecat/learn/pipeline-termination).
