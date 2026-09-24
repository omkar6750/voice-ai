---
id: RFC-0013
title: Live call monitoring and listen-only audio
status: Proposed
version: 1
date: 2026-09-24
authored_by: codex
related: [RFC-0004, RFC-0006, RFC-0011]
---

# RFC-0013 · Live call monitoring

## Goal and boundary

An operator opens one active run to hear the mixed call and watch finalized transcript, selected lifecycle events and redacted pipeline logs. This is monitoring, not a browser participant: no microphone uplink, barge-in or call-control commands on the monitor socket. The monitor never changes call timing.

The existing REST timeline remains source of durable evidence. WebSocket delivers live deltas and audio only while connected. Historical audio comes from the three recording artifacts after finalization. A call can complete without any monitor connected.

## Connection and authentication

1. Browser uses its in-memory operator Bearer token to request a short-lived, single-use monitor ticket via POST /api/v1/runs/{run_id}/monitor-ticket. Backend authorizes run access and restricts ticket to that run, mode and expiration.
2. Browser opens WSS /api/v1/runs/{run_id}/monitor and sends the ticket as its first JSON frame. Backend sends no data until the ticket is validated within a short timeout. Browsers do not support custom Authorization headers on the native WebSocket constructor. Neither the operator token nor ticket enters a URL or access log.
3. Backend verifies Origin, run ownership/active state, one-time ticket and optional viewer limit. Reconnect obtains a new ticket. On logout or run termination, close the socket and clear audio buffer.

These routes are required additions, not implemented APIs. First local deployment may use in-process tickets. A separate worker/process will require a shared authenticated relay; do not introduce Redis merely for a single-process POC.

## Stream protocol

One WebSocket per viewed run. Versioned JSON control messages carry run status, exchange/message finalization, span/tool completion, flow changes, redacted log lines, audio format, heartbeat, and stream cursor. Binary messages carry mixed mono signed 16-bit PCM with sequence and monotonic media timestamp. Header identifies protocol version and audio format; no raw modem framing reaches browser.

The runtime taps the same decoded capture path used for caller/agent recordings, after modem PCM conversion. It publishes a mixed stream from actual heard audio, not the text destined for TTS. Each viewer has a bounded queue; when slow, drop audio frames for that viewer and report a gap. Never block Pipecat, modem reads or evidence writes. Transcript/log events follow their own bounded delivery policy and can be recovered through REST. Broadcast fanout is scoped to a run.

Browser AudioWorklet buffers and resamples 8 or 16 kHz PCM to the playback device sample rate. Start muted with an explicit Listen button, volume control, buffering/connection indicator and dropped-audio notice. Browser autoplay rules require user gesture. The UI distinguishes generated text, finalized speech and actual playback. Audio is live only; no reconnect replay from WebSocket.

## Ordering and recovery

Each durable event has run-scoped sequence/cursor. On connect, load GET /api/v1/runs/{run_id}/timeline, then merge events after that cursor. On reconnect, fetch REST timeline again and deduplicate by stable IDs. Provisional STT revisions may be transient but never overwrite finalized transcript. Redacted debug lines are opt-in per call and have a bounded ring; they are not durable trace records unless pipeline-log capture is enabled.

Run ended and evidence flushed are separate signals. Keep the page connected until final evidence is committed or an incomplete-evidence condition is reported. Once closed, render stored transcript/spans and available artifacts.

## Audio and privacy limits

No audio data in PostgreSQL or generic JSON events. Existing artifact retention governs completed recordings; live stream is not stored by the monitor. Log redaction must happen before fanout. Secrets, raw LLM headers and token values cannot appear in events. The operator UI must clearly indicate live listening and the configured recording status. Deployment and use must follow applicable call-consent policy.

## Acceptance

- A real API-dispatched modem call yields audible caller and agent audio in the browser without changing call timing.
- Opening/closing/reconnecting a monitor does not affect the call; a slow viewer drops its own frames only.
- A viewer sees finalized transcript, tool outcomes, interruptions and status in order, and can recover after reconnect without duplicate messages.
- Wrong/expired/reused tickets fail; no credential enters WebSocket URL or access logs.
- Missing audio tap, absent transcript evidence and disabled pipeline logs show distinct UI states.
