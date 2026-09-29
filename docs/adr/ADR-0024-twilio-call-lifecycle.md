---
id: ADR-0024
title: One Twilio close owner and independent carrier facts
status: Accepted
version: 1
date: 2026-09-29
related: [RFC-0003, ADR-0007, ADR-0021]
---

Twilio uses a runtime-owned media session rather than Pipecat's stock automatic
hangup. The session owns ordered stream writes, the final playback mark, bounded
drain, one REST completion attempt, and a separate Call-resource read. End/Cancel
serialization and supervisor/endpoint finally blocks join the same close task.
An uncertain write is not retried. Release is confirmed only by a verified terminal
provider state; resource/recording cleanup failure is separate.

Retain Pipecat's mu-law codec/resampling. The transport Adapter changes only
graceful input stop: stop audio processing but retain the reader until output
drain finishes. Pinned Pipecat 1.11.0 otherwise tears down the shared socket too
early. Installed-transport tests are the upgrade gate for this private SDK seam.
Cancellation keeps the immediate stock teardown; the finally owner still tries
carrier release when output serialization cannot run.

Marks returned after clear are invalidated, never counted as playback. A matching
final mark means preceding carrier-buffered media was processed; it is not proof
the human heard, understood, or accepted the response. External stream loss stays
`disconnect_unknown`, not invented caller disinterest. Run success requires the
native terminal/agent intent and pipeline completion, not Twilio `completed`.

Callbacks authenticate against the configured canonical HTTPS/WSS URL using the
Twilio SDK; missing configuration fails closed. WSS permits the documented
trailing-slash signature fallback only. Account/call identity, start format and
run/correlation parameters must match. Lock Call before Run consistently for
callback, media claim, dispatch reconciliation and finalization. The media claim
and attachment commit together; terminal/duplicate streams cannot start a worker.
Provider event sequence and terminal non-regression rules prevent late callbacks
from undoing an already ended call.

Outbound create is fenced in storage before the external write. Both dispatch
entry points use one Module. Callback state is refreshed after create returns,
never reset to dialing. Network/timeouts/cancellation stay uncertain in attempt
metadata, with no automatic redial; a delayed legitimate media stream can still
claim the queued Run. SDK HTTP retries are disabled and waits are bounded.

Offline tests do not replace PostgreSQL concurrency, deployed TLS/signature,
carrier playback or live-account verification. Restart release reconciliation and
operator handling of an uncertain create without a known SID remain explicit
follow-ups. No automatic callbacks or dashboard WebSocket monitoring are added.

Official references: [Media Stream messages](https://www.twilio.com/docs/voice/media-streams/websocket-messages),
[Call resource](https://www.twilio.com/docs/voice/api/call-resource),
[request security](https://www.twilio.com/docs/usage/security), and
[Python HTTP client](https://github.com/twilio/twilio-python/blob/main/twilio/http/http_client.py).
