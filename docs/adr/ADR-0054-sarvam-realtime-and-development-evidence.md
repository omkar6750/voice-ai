# ADR-0054: Sarvam realtime and development evidence

Status: Accepted

Date: 2026-10-08

## Decision

Sarvam voice calls use `SarvamRealtimeSTTService` for `saaras:v3-realtime` and
`saaras:v4`, raw PCM, and provider VAD. Pipecat owns wire-message buffering.
The legacy per-frame WAV service is removed. New saves and runtime construction
reject `saaras:v3`. Historical configurations remain readable; cloning an old
version upgrades only the new draft to `saaras:v3-realtime`. Published snapshots
remain immutable. Both realtime models expose the same VAD settings in the editor.

In `VOICE_ENV=dev` (also `development` or `local`), run evidence, provider failures,
SDK messages, and exception traces preserve their content. Redact API authentication
keys by field name and by registered value before logging or persisting them.
Register environment and resolved per-run provider keys before provider construction.
Keep run IDs, credential references, transcripts, prompts, and provider request IDs
visible. Retain full provider errors in diagnostic metadata; the existing 2000-character
summary field stays bounded. Development captures JSON request evidence and pipeline
logs even when optional production capture is disabled; audio bodies are not expanded.
Production keeps the existing strict operational-log and evidence policy.

## Evidence

The failed phone recording replayed through the old 20 ms WAV path connected but
produced no transcript. With the installed realtime service and the same audio,
v3-realtime produced a final transcript and a caller inference context.

References: [Realtime protocol](https://docs.sarvam.ai/api/api-guides-tutorials/speech-to-text/realtime-streaming)
and [API/format matrix](https://docs.sarvam.ai/api/api-guides-tutorials/speech-to-text/which-api-to-use).
