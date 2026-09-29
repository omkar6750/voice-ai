# Handoff 001: call termination and end-call lifecycle

## Objective

Determine the correct end-call state machine for browser/WebRTC, SIM7600, and
Twilio calls. Produce an implementation-ready plan covering the `end_call`
tool, terminal nodes, caller hangup, transport disconnects, playback completion,
modem hangup, Twilio REST status, and cleanup/evidence finalization.

## Current implementation

The native host is in:

- `packages/voice_runtime/voice_runtime/execution/native.py`
  - `NativePipelineHost._handler("end_call")`
  - `NativePipelineHost.converse()`
  - `NativePipelineHost._record_call_termination()`
  - `NativePipelineHost.close()`
- `packages/voice_runtime/voice_runtime/telephony/driver.py`
- `packages/voice_runtime/voice_runtime/telephony/session.py`
- `packages/voice_runtime/voice_runtime/telephony/sim7600.py`
- `packages/voice_runtime/voice_runtime/telephony/twilio.py`
- `apps/api/voice_api/services/browser_session_service.py`
- `apps/api/voice_api/api/v1/endpoints/telephony.py`
- `apps/api/voice_api/api/v1/endpoints/reconciliation.py`
- `packages/voice_runtime/voice_runtime/execution/runner.py`

Current native behavior is approximately:

```python
if name == "end_call":
    self._call_hung_up = True
    self.tracker.diagnostic(code="agent_hangup", ...)
    await self.worker.queue_frame(EndFrame())
    return {"status": "ok"}
```

The SIM7600 driver performs modem cleanup after the pipeline returns. The
browser path treats WebRTC disconnect as transport termination. Twilio has call
and stream status callbacks, but the native end-call behavior has not been
verified against Twilio’s actual REST/media lifecycle.

`NativePipelineHost.close()` currently closes the worker and then ends the
active visit/exchange as completed. This is too coarse for failures,
cancellation, mid-flow disconnect, and uncertain transport cleanup.

## Web-research instructions

The research agent has no repository or CLI access. Search public official
Pipecat documentation/source for `EndFrame`, `TTSStoppedFrame`,
`BotStoppedSpeakingFrame`, `PipelineTask`, and Pipecat Flows
`end_conversation`. Search official Twilio Voice and Media Streams
documentation for REST call termination, stream status callbacks, and final
call status. Search browser/WebRTC documentation for transport close and peer
connection termination semantics.

Use documentation matching the project’s Pipecat 1.11-era APIs when possible.
If current docs differ, explain the version difference and identify the API
that should be verified by the implementation agent.

Answer precisely:

1. Which frame/event proves that final TTS audio has finished playing?
2. Does `EndFrame` stop upstream generation immediately, or allow queued audio
   to drain?
3. What is the supported Pipecat Flows action ordering for normal close versus
   immediate caller hangup?
4. For browser WebRTC, which event is authoritative: client disconnect,
   transport close, worker completion, or application stop request?
5. For Twilio, does stopping the Pipecat pipeline end the Twilio call, or must
   the application call Twilio’s REST hangup endpoint? How do media stream status
   and call status interact?
6. For SIM7600, when should `hangup()` run relative to pipeline cancellation and
   USB audio shutdown?
7. Which statuses should be persisted for terminal-node completion, caller
   hangup, agent hangup, provider failure, network failure, cancellation, and
   uncertain cleanup?
8. Is a two-phase close model needed: close requested, final audio drained,
   transport hangup requested, transport released, and outcome finalized?

## Required deliverable

Return an implementation plan with:

- a state-transition table;
- event/frame ownership for each transport;
- exact Pipecat/Twilio APIs and versions;
- evidence fields and diagnostic codes;
- timeout and idempotency rules;
- unit, browser, SIM7600, and Twilio test scenarios;
- files to change, in order.
- links and quoted API names supporting every Pipecat/Twilio claim;
- a recommendation for distinguishing `caller_ended_mid_flow`,
  `caller_ended_after_terminal`, `agent_completed`, `agent_requested_hangup`,
  `provider_failure`, `network_failure`, `cancelled`, and `uncertain`.

Do not implement code in the research task.
