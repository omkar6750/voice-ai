# Local text-only agent tests

Open an agent version on http://localhost:5174 and select **Chat test**. Save draft edits first. Choose a contact and optional international WhatsApp override, a starting node, caller background and a manual testing scenario. **Live tools** means WhatsApp sends and bookings are real.

API: 127.0.0.1:8002. Existing runtime: 127.0.0.1:8001. Local PostgreSQL: 55433. Migration: 0046_text_tests. Start the native services with scripts/start-local-services.ps1. Nothing is deployed or pushed by this feature.

Messages stream over a single-use ticket WebSocket. Sending during generation interrupts it. Stop response preserves partial output. Opening saved history does not execute tools; Connect / resume restores a safe checkpoint into a new attempt when needed. Disconnected sessions pause after 30 seconds. An unresolved write blocks resume and retains history for inspection.

Click a message or tool event to inspect the exact context, arguments, results, routing and trace timing. Details can be temporarily unavailable until acknowledged persistence. Retry details after the message is Saved. Saving delayed means the runtime retains unacknowledged records; do not assume database persistence until Saved.

Setup and execution errors appear inline with stage, timestamp and diagnostic ID. Runtime logs are in data/local-service-logs/runtime.err.log and data/logs/voice-runtime.jsonl. API logs are in data/local-service-logs/api.err.log and data/logs/voice-api.jsonl. Credentials remain redacted. Existing VOICE_ENABLE_INBOUND_API_LOGS, VOICE_ENABLE_OUTBOUND_API_LOGS, no-truncate flags, VOICE_DEBUG_PERF and VOICE_LOG_LEVEL apply equally.

VOICE_RUNTIME_MIN_FREE_SPOOL_BYTES defaults to 536870912. Admission uses usable free disk space and existing spool quota/queue limits; total drive occupancy alone does not reject calls.

Text tests do not validate acoustic interruptions, STT recognition, TTS quality or real modem audio. Operator testing of live WhatsApp/calendar effects remains required.
