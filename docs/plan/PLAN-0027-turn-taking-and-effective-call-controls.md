---
id: PLAN-0027
title: Turn-taking and effective live call controls
status: Proposed
date: 2026-09-27
related: [PLAN-0020, PLAN-0012]
---

# Turn-taking and effective live call controls

## Decisions and evidence

The user reports carrier audio is clear, without echo or backpressure; do not keep those as leading explanations for oversensitive interruption or silence. Still verify event timing, because clear audio alone does not identify VAD/turn-management causality. Skip Krisp VIVA: SDK access must be requested and it is not wanted now. Silero remains the baseline.

The dashboard currently saves `call_limits.interruptions_enabled` and `idle_timeout_secs`; the native host does not consume them. The flags must either become effective or be removed/marked pending. The user wants them fixed. Do not claim that changing them already tunes behavior. `max_duration_secs` is used by the runner and should remain.

## Implementation sequence

1. Build a causal trace for real and browser-demo turns: VAD speech-start/stop, STT partial/final, user-turn start/end, LLM request/start/finish, TTS start/finish, playback start/finish, interruption reason, and idle timer state. Separate a pipeline break from “agent keeps listening” and from benign noise barge-in.
2. Define `interruptions_enabled` semantics in one place: whether speech interrupts TTS, which Pipecat interruption strategies/frames are used, and what happens when STT produces no transcript. Map saved setting to supported transport/aggregator configuration; validate any startup-only setting at build time. Preserve safe caller hangup independent of this flag. Add an operator explanation that disabling barge-in trades responsiveness for fewer false cuts.
3. Implement `idle_timeout_secs` with Pipecat idle-user behavior or a tested local timer tied to completed user/assistant turns. Reset it on true user activity, not ambient VAD noise. On idle, give bounded reprompt(s), then a clean close; prevent concurrent LLM starts and cancel timer on hangup. Allow explicit disabled mode only if the contract/UI supports it.
4. Inspect installed Pipecat support for interruptions with no transcript and configure an empty-turn strategy. The earlier documentation may describe newer API than installed 1.11; feature-gate or upgrade deliberately, never attach a nonexistent parameter. Test the specific symptom: sound stops agent but STT yields nothing, followed by a graceful resumption or reprompt.
5. Add a bounded demo-only tuning panel for Silero start/stop/confidence/min volume plus supported turn/interrupt thresholds and live effective settings; show presets and guardrails, not an unrestricted maze. Record which configuration was used for each run. Compare controlled playback of identical carrier samples at different settings.
6. Keep voicemail detection as a separate later capability: detect machine/answering-service signals, suppress sales flow, and end/leave message according to approved campaign policy. Do not conflate voicemail with idle timeout or VAD threshold.

## Implementation note (2026-09-27)

The live host now applies saved interruption and idle-timeout settings to Pipecat's user-turn aggregator; one idle reprompt precedes bounded cancellation. Unit tests cover both settings and the idle sequence. Current Pipecat 1.11 `LLMUserAggregatorParams` has no `empty_user_turn` field even though the current online interruptions guide documents it. Do not expose that control until a deliberate Pipecat upgrade or a tested equivalent is available. The demo tuning panel, carrier validation, and voicemail policy remain open.

## Tests and acceptance

- Unit tests for flag on/off, no-transcript interruption, short noise during TTS, backchannel, real caller barge-in, silent caller, idle timer reset, stalled pipeline and hangup.
- Browser-demo matrix and SIM7600 carrier call matrix capture false interruptions, time to agent response, dead air, and ability to recover. User-reported clear audio is treated as baseline, not proof no software fault exists.
- Dashboard round-trip test proves saved controls change actual runtime settings and run evidence, not merely JSON.

Refs: [Pipecat interruptions](https://docs.pipecat.ai/pipecat/fundamentals/interruptions), [idle users](https://docs.pipecat.ai/pipecat/fundamentals/detecting-idle-users), [voicemail](https://docs.pipecat.ai/pipecat/fundamentals/voicemail), [examples](https://docs.pipecat.ai/pipecat/examples/overview), [recipes](https://docs.pipecat.ai/pipecat/examples/recipes).
