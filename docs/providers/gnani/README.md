# Gnani and Isoquant provider setup

The five reference pages in this folder are copies of the user-supplied Gnani
documentation, saved on 2026-10-02. They describe vendor APIs; the integration
below describes what this application implements.

## Configure a conversation

1. In Settings → Provider credentials, add named **Gnani** and **Isoquant** keys.
   Credentials are write-only, encrypted, organization-scoped, and pinned to a
   version when execution is resolved. The browser receives metadata only.
2. In an agent draft's model settings, select Gnani STT with
   `gnani-prisma-v2.5`, and a supported recognition language such as `hi-IN`.
3. Select Gnani TTS with `timbre-v2.5`, a voice such as `Nalini`, and `hi-IN`.
   Pace is forwarded as Gnani `speed` and must be between 0.85 and 1.15.
   Choose the stage credential for both STT and TTS; the same stored key can
   be bound to both stages.
4. Select Isoquant `glm-5.3-flash`, low/high/max reasoning effort and an output
   allowance. Start with 1024 output tokens for a short conversation: reasoning
   consumes the allowance too. ZDR is required and returned reasoning is hidden.
   Bind its credential separately for main LLM, classifier, or summarizer.
5. Optionally select an LLM fallback and its separate stage credential. Save and
   publish the draft, then run a browser voice test through the API/runtime split.

Gnani supports the application's 8 kHz telephony and 16 kHz browser PCM paths.
STT reframes the transport's 20ms input into 1024-byte PCM messages, retaining
only the remainder. TTS requests raw mono signed 16-bit PCM at the pipeline's
sample rate, preserves whole-sample boundaries and requires a completion event.

## Runtime and API ownership

The API resolves and decrypts pinned credentials. Its existing authenticated
runtime dispatch sends stage keys once to the separate runtime, which keeps
them in memory. Gnani SDK imports live only in the runtime adapter. No new
database migration or browser key handling is needed.

The installed `pipecat-gnani==0.5.12` plugin imports `_NotGiven`, removed from
Pipecat 1.11's settings module. Instead, local services use Pipecat's public
`STTService` and `TTSService` classes around `gnani-vachana==0.7.9`. The SDK's
WebSocket generator closes on cancellation, giving the pipeline interruption
cleanup. Its raw logger is disabled so it cannot bypass safe runtime logging.

REST/SSE and voice cloning are documented vendor alternatives, not exposed
runtime options. The supported application transport is WebSocket for both
speech stages.

## Failures and fallback

The existing first-token LLM fallback accepts Isoquant as primary or fallback.
It can switch on connection/status errors, an empty truncated stream, or the
configured first-token deadline. It never switches after emitting text or tool
fragments. Generated partial replies are not replayed.

Speech errors mark the processor unusable and stop the session through the
existing pipeline policy. Speech is not automatically replayed or switched
between vendors after an uncertain send. STT handshake waits at most 15 seconds;
each TTS synthesis waits at most 30 seconds and requires its terminal event.

HTTP 402 maps to `provider_quota_exhausted`; 401/403 to authentication failure;
429 to throttling or exhausted quota; 5xx to provider unavailability. Wrapped
SDK handshake exceptions are inspected through a bounded cause chain. Safe
request IDs and retry delays are retained for the new adapters; raw provider
error bodies and secrets are excluded from evidence.

Live vendor latency, audio quality and real modem behavior require a configured
credential and a manual test. Offline checks do not spend provider credit.

## References

- [Pipecat plugin](pipecat-plugin.md)
- [Quick start](quick-start.md)
- [Python SDK overview](python-sdk.md)
- [STT SDK](speech-to-text.md)
- [TTS SDK](text-to-speech.md)
