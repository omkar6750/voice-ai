# ADR-0021 · Browser test calls use Pipecat WebSocket transport

Status: Accepted
Date: 2026-09-28
Related: [ADR-0008](ADR-0008-browser-session-version-resolution.md), [RFC-0014](../rfc/RFC-0014-clerk-b2b-onboarding-and-tenant-boundaries.md)

## Context

The browser test call used SmallWebRTC with an SDP/ICE HTTP handshake. The
planned single Render web service exposes HTTPS and WebSockets but does not
route a separate inbound WebRTC media port. The demo needs one browser call
at a time, locally and remotely, without operating TURN or Daily.

## Decision

Use Pipecat's `FastAPIWebsocketTransport` with its protobuf serializer in the
API and `@pipecat-ai/websocket-transport` in the dashboard. Browser audio and
RTVI control use one WebSocket. The native pipeline, resolved agent snapshot,
evidence, and run lifecycle remain unchanged. Twilio's media WebSocket and
SIM7600 audio are separate transports and are unaffected. No Socket.IO layer
or handwritten PCM wire format is introduced.

In-process browser, Twilio, and SIM7600 calls persist evidence and artifacts
through local operations rather than loopback HTTP. They do not need
`VOICE_RUNTIME_SERVICE_TOKEN`; external worker-facing routes still require it.
Human callback slots use a separate `VOICE_CALLBACK_SLOT_SIGNING_KEY`.

The authenticated session-creation route is followed by a short-lived,
single-use ticket route. The WebSocket accepts only configured origins and
consumes the ticket before accepting. Clerk and runtime-service bearer tokens
never appear in its URL. The demo process permits one active browser call.

## Consequences

One HTTP/WebSocket port works both behind Vite locally and behind Render TLS.
The transport is simpler to deploy, but TCP head-of-line blocking and lost
WebRTC media features can increase latency or degrade speech on poor networks.
It is a demo choice, not a recommendation for multi-user production voice.
Provider credentials and a verified Clerk user are still needed for a live
end-to-end call. The five-minute browser session limit remains.
