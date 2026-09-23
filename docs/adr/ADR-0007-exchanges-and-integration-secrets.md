---
id: ADR-0007
title: Exchange evidence and backend-only action credentials
status: Accepted
version: 2
date: 2026-09-23
related: [RFC-0003]
---

Use application exchange IDs independently of Pipecat timeout-based turns.
Messages and spans are linked, not inferred by timestamps. Preserve overlapping
execution, interrupted playback, opening and background result provenance.

Fernet ciphertext and key ID live in integration_secrets; deployment owns keys.
No model-provider secrets in the database or frontend. WhatsApp sends and
receipts live in tool evidence. Inbound text is discarded, and unknown direct
message windows require templates. Retain reusable media separately from calls.

## Schema review amendment

Updated in place at the user's explicit request; RFC-0003 version 2 contains the
review reasoning. This is an exception to immutable ADR editing.

Run is conversation execution across browser and telephone channels. Optional Call
owns provider-neutral telephone lifecycle, provider identity and typed diagnostics.
Persist internal call ID before dialing; modem correlation ID is distinct from
nullable external provider call ID. Do not infer cloud-provider support from schema.

Attach exchanges and finalized speaker messages to Run. Keep exchange groupings,
including greeting and delayed results, separate from speaker turns and node visits.
Keep exact sanitized LLM context on operations, not in the readable transcript.

Dedicated flow visits reference timing spans and actual transition triggers. No
separate node-change reason or LLM-generated reason. Enrich existing trace spans
with typed metrics and OTel identity; do not duplicate each provider operation.
Ordered tool results preserve finality, originating inference/function call and
context consumption. Only intermediate results supplied to context need persistence.

Exact WhatsApp sends and account-scoped deduplicated receipts remain tool evidence;
no outbound messaging subsystem. Fernet is authenticated encryption, not envelope
encryption. Deployment keyring stays outside the database. Reusable media remains
separate from expiring call artifacts; shared safe storage utilities are sufficient.

Persist classification/summary/fact history with source boundaries and sanitized
final Run state. Live state stays in memory. Callbacks pin agent version, default
automation off and permit one automatic attempt in the due window. Atomic claims
and restart reconciliation must never redial uncertain external attempts.

Debug detail stays optional and file-only. No raw event table, historical KB corpus,
inbox, Redis, object storage requirement or external tracing backend for this POC.
