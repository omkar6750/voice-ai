---
id: ADR-0059
title: Observed telephony release evidence and bounded voicemail detection
status: Accepted
date: 2026-10-09
---

Keep execution completion separate from telephony release cause. Busy, no answer,
rejection and voicemail are explicit outcomes on a failed/uncompleted Run, without
adding database status values. Terminal completion remains independent of who
disconnects. Never infer a caller hangup from NO CARRIER or an empty CLCC list.

The SIM7600 adapter owns one serial reader at a time. Its idle monitor and command
reader share the command lock and fragmented-line buffer. Persist call-control and
registration observations through the organization-scoped diagnostic spool:
disconnect/release URCs, active-call clearing, local hangup, registration changes,
and serial I/O failures. Do not persist unrelated or unknown URCs, or emit routine
AT command/response lines to operational logs. The final
snapshot holds only the last 64 relevant observations and explicitly reports
truncation. No claim is made about codes the modem never emitted, events before
ownership or during USB/power loss, or post-retention availability.

Capture CEER first under a bounded deadline before cleanup can overwrite a remote
release report. Retain query failures and unknown registration/SIM readings.
Capture locally initiated release after the hangup, preserving its timestamp and
the preceding disconnect observations. Naked CEER numbers are ambiguous between
cause domains; preserve them without guessing. Explicit supported cause text can
identify busy/no-answer/rejection/network failure. Normal clearing is only a
likely remote hangup when network evidence is missing. A separate high-confidence
“other side ended” outcome requires no earlier local hangup, a release observation,
known voice registration, CSQ RSSI of at least 15 at release, no query errors, and
no observed voice-registration loss or serial I/O error. This is an operational
attribution rule, not a carrier-provided initiator identity. Later cleanup
must not change the frozen release snapshot. A network-ended release alone does
not prove a network fault. Firmware-specific VOICE CALL END reports are retained
but are not interpreted using a different modem family's cause table.

Phone calls use Pipecat 1.11 VoicemailDetector with a separate instance of the
configured main LLM and its existing credential, no conversation tools, short
output and no fallback. Browser and text tests skip this detector. Configuration
defaults enable detection and limit the initial speech wait to five seconds;
operators can disable it or adjust the deadline in Audio settings. No published
row or agent prompt is rewritten. The default is a runtime/config interpretation
for configurations that omit the new fields.

Human/voicemail verdicts are model assessments, not modem certainty. Unknown,
timeout and classifier error release speech without claiming a human answered.
Late verdicts cannot hang up a call after this fail-open decision. Detected
voicemail cancels the owning worker directly; it does not push EndFrame through
the detector's closed gates and does not leave a message or redial. The compatibility
adapter's notifier hooks are tested against Pipecat 1.11 and must be revisited on
a Pipecat upgrade. Detection incurs an additional short LLM operation and may
delay initial speech up to the configured bound. No live carrier/provider behavior
is established by fake-modem tests.

The Runs list labels Busy, No answer, Call rejected, Voicemail, local hangup,
network/modem failure, and the high-confidence other-side release while retaining
the underlying execution status. The inspector shows a short explanation and keeps
technical termination evidence collapsed until requested. Historical runs show
missing evidence; they are never reclassified using the current configuration.

References: SIMCom SIM7500/SIM7600 AT Command Manual V3, sections 4.2.1,
5.2.7–5.2.8; V1.01 appendix 17.2; Pipecat Context Hub VoicemailDetector API.

## 2026-10-10 — Recovery contract and independent cleanup delivery

Runtime probes, reconciliation and API endpoint JSON storage share the strict
ModemEndpointStatus contract. Missing historical registration-known flags remain
unknown; runtime responses with incompatible fields report a service mismatch,
not an operator input validation error. The dashboard distinguishes stale status
from offline hardware and uncertain ownership from an active call.

Tool-result context notification is idempotent per result, including transition
callbacks. A duplicate framework notification must not create a second immutable
delivery timestamp or repeat a transition. Evidence identity validation remains
strict in storage.

The Pipecat voicemail detector is a parallel pipeline with its own assistant
aggregator. Conversation tool broadcasts otherwise reach both that aggregator
and the main assistant aggregator, invoking the same context callback twice.
The local compatibility adapter bypasses conversation context/tool control in
both directions, and other upstream frames bypass the classification branches
apart from synchronized lifecycle frames. Caller transcripts and shutdown frames
still fan out normally. LLM evidence records only the downstream tool-start
broadcast, so the same call ID is not displayed twice in the model response.

The Pipecat 1.11 TTS gate holds speech outside the processor queues. Its local
replacement clears held audio, text and speech-boundary frames on interruption,
fences an in-progress notifier release by epoch, and rejects late output from
canceled TTS context IDs. Fresh responses keep their order and pass normally.
Shutdown invalidates pending speech before lifecycle frames pass through. This
compatibility seam is covered before/during/after release and must be revisited
on dependency upgrades. Context-free buffered frames are cleared too; later
context-free provider output cannot be attributed to a canceled generation and
continues to rely on the TTS service's own cancellation.

Terminal ownership release can synchronize without transcript records, context
updates or diagnostic batches. Rejected evidence cannot block confirmed cleanup;
unsaved evidence stays in the spool and is explicitly marked incomplete. Pipeline,
media and controller cleanup are attempted independently with bounded deadlines.
Storage close failures do not invalidate already confirmed transport release.
Run, Call and dispatched Callback status follow the confirmed cleanup result.
Operator stops cancel and await the pipeline's PCM workers before issuing modem
hangup or disabling USB audio. Pipeline shutdown failure still attempts modem
release; it must not skip physical cleanup. This prevents pending playback writes
from turning a successful operator hangup into a pipeline failure.
Evidence rejection, execution lease expiration and the configured duration limit
have distinct causes. An internal timeout is not a duration-limit event, and an
execution failure in the terminal node is not successful completion. Lost power,
USB or service connectivity can still prevent release confirmation; those cases
retain uncertain ownership until fresh worker and modem verification succeeds.
