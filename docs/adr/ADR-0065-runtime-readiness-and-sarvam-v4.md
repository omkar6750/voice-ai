---
id: ADR-0065
title: Probe runtime admission and isolate Bulbul v4 compatibility
status: Accepted
date: 2026-10-15
related: [ADR-0006, ADR-0007, ADR-0064]
---

# Decision

Browser and chat startup poll an authenticated API readiness resource before
creating sessions. The API probes its configured runtime health and authenticated
status with short timeouts. Readiness never clears assignments, releases leases,
redials or retries mutation requests. Dispatch repeats the check to handle restarts.
Gateway failures after mutations remain uncertain until reconciliation.

Keep Pipecat at 1.11.0. A repository-owned Bulbul v4 subclass changes only
construction and configuration. Pipecat owns streaming, completion and interruption.
V4 explicitly selects the model in the WebSocket query, an approved persona and
linear16 PCM at the existing 8/16 kHz run rate. Existing v3 configurations remain
unchanged. The dated official catalog contains 222 unique persona IDs.

Live protocol checks take precedence over inconsistent guide snippets: the tested
endpoint accepts `target_language_code` and string `speech_sample_rate`. Buffer 20
was rejected with 422; use 30–200, with 30 for new v4 drafts and unchanged upstream
50 when omitted. Chunk length remains 50–500, default 150. V4 omits temperature.

Server-only turn timing is an explicit draft setting. Missing settings retain
local Silero timing. Both use Sarvam external turn strategies and JSON keepalive
at 30 seconds. Local VAD metrics are unavailable in server-only mode.

STT connection diagnostics retain counters, timestamps, safe request IDs and
normalized errors in the existing evidence metadata contract. They never retain
caller text, audio, headers or raw close reasons. An unusable STT service ends the
pipeline rather than discarding caller audio indefinitely. No credential failover
or audio replay is added.

# Limits

Audio sent successfully proves a socket write, not provider ingestion. A missing
final transcript is distinct from a transport failure. No historical failure is
assigned an authentication, quota or disconnect cause without evidence.

This does not add word-level TTS alignment, change RLS/Storage authorization, or
migrate published agents. See [ADR-0064](ADR-0064-storage-and-organization-authorization.md).
