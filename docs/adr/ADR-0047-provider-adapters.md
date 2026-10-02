# ADR-0047: Isoquant and Gnani runtime adapters

Accepted 2026-10-02 for the provider integration requested by the user.

Use Isoquant Chat Completions through a local OpenAILLMService subclass. This
retains Pipecat's existing conversation/tool aggregation, metrics, and main LLM
first-token fallback. Require ZDR, omit returned reasoning, explicitly bound
output tokens, and validate low/high/max reasoning effort. Incomplete streams
raise an error; fallback cannot replay already-emitted text or tool fragments.

Use local Pipecat STTService/TTSService subclasses around Gnani's core SDK
WebSocket clients. The official plugin 0.5.12 imports a private settings type
removed in Pipecat 1.11 and cannot be loaded with the application's dependency.
Avoid vendor-package patches or a global Pipecat compatibility monkeypatch.
Pin the compatible core SDK range and validate its serialized request shape,
PCM framing, terminal events and cancellation with offline socket tests.

The API owns typed configuration, provider capabilities and encrypted credential
resolution; the separate runtime owns SDK clients and media. Extend the existing
stage-key handoff and generated OpenAPI contracts. Keys remain absent from
published snapshots, browser contracts and persisted runtime evidence.

Expose Prisma v2.5 STT and Timbre v2.5 TTS at 8/16 kHz. Reject unsupported
model/language/voice/speed values before network requests. Stop on speech
failure instead of replaying an uncertain audio send. Bound connection and
synthesis waits, close sockets on cancellation, and suppress raw SDK logs.

REST/SSE, voice cloning and cross-provider speech fallback are future features;
their vendor documentation is retained locally without advertising them as
working runtime settings.
