---
id: PLAN-0031
title: Typed call outcomes and transport-safe termination
status: Proposed
date: 2026-09-28
related: [PLAN-0023, PLAN-0013, PLAN-0030, ADR-0013, ADR-0021]
---

# Typed call outcomes and transport-safe termination

## Decision

Do not expand the existing `Run.status` and `Call.status` columns into a large
set of provider-specific statuses. Keep the operational lifecycle compatible:

```text
queued -> claimed -> running -> completed | failed | uncertain
```

Add typed semantic facts alongside that lifecycle:

- `outcome_code`: why the call ended;
- `termination_intent`: who requested termination and why;
- `transport_state`: active, release_requested, released, or unknown;
- `audio_state`: not_started, speaking, drained, interrupted, or unknown;
- `outcome_confidence`: confirmed or uncertain.

The API and dashboard can then explain “failed because the caller left
mid-flow” without breaking queries that depend on `status == failed`.

## Required outcome vocabulary

The initial vocabulary should be small and transport-neutral:

| Outcome code | Operational status | Meaning |
|---|---|---|
| `terminal_completed` | completed | The configured terminal node completed and transport release was confirmed. |
| `caller_ended_after_terminal` | completed | The caller disconnected after terminal completion was already recorded. |
| `agent_requested_hangup` | completed | The agent intentionally ended the call and transport release was confirmed. |
| `caller_ended_mid_flow` | failed | The caller/remote transport ended before terminal completion. |
| `caller_idle_timeout` | failed | The runtime ended an idle call after its configured policy. |
| `provider_failure` | failed | STT, LLM, TTS, or telephony provider failed. |
| `network_failure` | failed | The transport or provider connection failed. |
| `pipeline_failure` | failed | Pipecat/runtime failure without a more specific provider cause. |
| `cancelled` | failed | Operator, worker, or process cancellation stopped the call. |
| `transport_cleanup_uncertain` | uncertain | The worker cannot prove the endpoint/modem/call was released. |

`agent_hangup` and `remote_hangup` remain diagnostic/event codes, not the only
source of final outcome truth. The finalizer combines intent, flow progress,
transport observations, and cleanup result.

## Current failure seam

`NativePipelineHost._handler("end_call")` currently sets `_call_hung_up`, emits
`agent_hangup`, and queues `EndFrame`. `converse()` also treats a liveness
failure as remote hangup and `close()` always ends the visit/exchange as
`completed`. `execute_call()` currently assigns `completed` after `driver.call`
returns, even when the returned state or cleanup does not prove successful
completion.

The implementation must not put more branching into `native.py`. Add small
modules/protocols:

- `execution/termination.py`: typed termination intent, observation, and
  outcome reducer;
- `execution/transport_release.py`: idempotent release coordination;
- `execution/finalization.py`: one finalization function shared by SIM7600,
  browser, and Twilio paths.

`native.py` should only report observations and request a close. It should not
decide the final database status.

## Verified provider semantics

The official Pipecat termination guidance confirms the important distinction:
`EndFrame` is graceful and drains pending frames; `CancelFrame` is immediate
and discards pending non-system frames. Pipecat also documents
`on_pipeline_finished` as the single cleanup point for both graceful and
cancelled shutdown, while the transport disconnect event is the place to tag
the reason. Use these facts in the implementation instead of inventing a
custom “TTS finished” signal in `native.py`.

Official references:

- [Pipecat pipeline termination](https://docs.pipecat.ai/pipecat/learn/pipeline-termination)
- [Twilio Call resource and status callbacks](https://www.twilio.com/docs/voice/api/call-resource)

Twilio’s official Call resource supports terminating an active call by
updating its status to `completed`, but its status callbacks are asynchronous
and may arrive separately from the runtime’s close request. Treat the REST
update as a release request and the callback/API observation as provider
evidence, not as the local finalizer itself.

## Close protocol

Use one idempotent close coordinator with these phases:

1. `open`: normal conversation is allowed.
2. `close_requested`: record intent and stop accepting new tool/LLM work.
3. `audio_draining`: for a normal agent close, wait for the documented final
   audio/playback signal with a bounded timeout; for caller/network failure,
   skip draining and cancel promptly.
4. `transport_release_requested`: queue/end the Pipecat pipeline and request
   provider/modem hangup exactly once.
5. `transport_released`: prove release using the transport’s status/callback.
6. `finalized`: reduce observations into outcome code, persist evidence, and
   close visit/exchange with the semantic result rather than unconditional
   `completed`.

Every phase transition is idempotent. A timeout produces an explicit uncertain
observation; it must not silently become successful completion.

## Transport adapters

Keep provider behavior behind a local protocol:

```python
class CallTransport(Protocol):
    async def request_release(self, reason: str) -> None: ...
    async def observe(self) -> TransportObservation: ...
```

- SIM7600 adapter owns modem hangup and USB audio stop ordering.
- Browser adapter reports WebSocket/WebRTC close and cannot claim carrier
  release beyond the browser transport it controls.
- Twilio adapter records call/stream callbacks and uses the Twilio call update
  operation only when the application intentionally terminates the call.

The driver remains responsible for adapter cleanup; the reducer remains
responsible for meaning. Do not make modem state, Twilio callbacks, or browser
disconnects directly mutate `Run.status` in separate code paths.

## Implementation order

1. Add typed runtime contracts and reducer tests with no database changes.
2. Add `outcome_code`, intent, transport, and audio fields to final-state API
   contracts; preserve old fields and nullable behavior during rollout.
3. Extract release coordination from `native.py`, `driver.py`, and provider
   endpoints behind the transport protocol.
4. Change native handlers to emit observations and close requests only.
5. Change `execute_call()` and browser/Twilio finalizers to call the shared
   reducer once, after release/evidence facts are known.
6. Add migration columns only if querying semantic outcome is required; retain
   the final-state JSON for backward-compatible replay and old runs.
7. Update the dashboard to show status, outcome, confidence, and evidence
   completeness separately.

## Regression tests

- terminal node followed by normal agent close;
- agent `end_call` called twice;
- caller disconnect before terminal node;
- caller disconnect after terminal node;
- pipeline/provider error during speech;
- normal close with playback timeout;
- cancellation during close;
- SIM7600 hangup failure and modem still active;
- Twilio call update failure and later callback;
- browser disconnect without a final application message;
- cleanup failure keeps `uncertain` and endpoint reserved;
- evidence delivery failure does not relabel a confirmed call outcome;
- concurrent close requests produce one release and one finalization.

## Non-goals

- No automatic redial.
- No provider-specific status strings in the core model.
- No large rewrite of `native.py`.
- No claim that low signal alone caused a termination.
- No change to classifier cadence or generic node actions.

## Acceptance criteria

- `close()` never unconditionally writes `completed`.
- Every terminal run has an outcome code and confidence.
- Unreleased or unverified transport remains `uncertain`.
- The same reducer is used by SIM7600, browser, and Twilio finalization.
- Existing status-based API consumers continue to work.
- Evidence completeness remains independent from call outcome.
