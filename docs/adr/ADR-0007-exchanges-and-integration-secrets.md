---
id: ADR-0007
title: Exchange evidence and backend-only action credentials
status: Accepted
version: 1
date: 2026-09-22
related: [RFC-0003]
---

Use application exchange IDs independently of Pipecat timeout-based turns.
Messages and spans are linked, not inferred by timestamps. Preserve overlapping
execution, interrupted playback, opening and background result provenance.

Fernet ciphertext and key ID live in integration_secrets; deployment owns keys.
No model-provider secrets in the database or frontend. WhatsApp sends and
receipts live in tool evidence. Inbound text is discarded, and unknown direct
message windows require templates. Retain reusable media separately from calls.
