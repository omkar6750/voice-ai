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
reader share the command lock and fragmented-line buffer. Record every observed
unsolicited line, including unknown types and repetitions, through the existing
organization-scoped diagnostic spool, independently of optional debug logs. Known
call-control URCs retain redacted fields; unknown/private payloads retain their
type and SHA-256 identity, with content redacted; small numeric status/cause fields remain visible. The final snapshot holds only the
last 64 observations and explicitly reports truncation; persisted diagnostics are
the full observed sequence. No claim is made about codes the modem never emitted,
events before ownership or during USB/power loss, or post-retention availability.

Capture CEER first under a bounded deadline before cleanup can overwrite a remote
release report. Retain query failures and unknown registration/SIM readings.
Capture locally initiated release after the hangup, preserving its timestamp and
the preceding disconnect observations. Naked CEER numbers are ambiguous between
cause domains; preserve them without guessing. Explicit supported cause text can
identify busy/no-answer/rejection/network failure. Normal clearing is only a
likely remote hangup when no earlier local hangup was observed. Later cleanup
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

The Runs list labels Busy, No answer, Call rejected and Voicemail while retaining
the underlying execution status. The inspector displays termination evidence and
the retained modem observation sequence. Historical runs show missing evidence;
they are never reclassified using the current configuration.

References: SIMCom SIM7500/SIM7600 AT Command Manual V3, sections 4.2.1,
5.2.7–5.2.8; V1.01 appendix 17.2; Pipecat Context Hub VoicemailDetector API.
