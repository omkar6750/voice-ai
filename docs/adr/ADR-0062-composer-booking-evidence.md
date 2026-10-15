---
id: ADR-0062
title: Authoritative booking evidence for WhatsApp composition
status: Accepted
version: 1
date: 2026-10-15
authored_by: codex
session: documentation-review-20261015
supersedes: ADR-0050 transcript-only input restriction
superseded_by: null
related: [ADR-0050, ADR-0025, ADR-0056]
---

# Context

This records the already implemented composer input contract and its existing tests.
ADR-0050 described the plain transcript as the only user message. Current code also
accepts structured booking results, which are necessary to distinguish a confirmed
appointment from a spoken promise, requested time or failed booking.

# Decision

Keep the complete finalized Caller/Agent transcript as a plain dialogue message.
When available, add a separate structured booking-evidence message with the returned
`book_callback` arguments and results. It is data, not instructions or an arbitrary
dump of model context, tool calls, summaries or facts. Only a confirmed booking result
establishes an appointment; failed, uncertain and merely requested times do not.

The main agent still chooses the template tool and optional recipient. The configured
composer stage returns the pinned dynamic fields. Exact keys, nonempty values, length
limits and required URLs validate before the WhatsApp broker is invoked. Composition
failure records diagnostics and does not send. Template-specific wording remains an
operator configuration, not a hard-coded conversational promise.

# Evidence

- [Composer implementation](../../packages/voice_runtime/voice_runtime/execution/whatsapp_composer.py).
- [Composer regressions](../../tests/unit/test_whatsapp_composer.py), especially
  `test_composer_receives_structured_booking_evidence`,
  `test_booking_evidence_preserves_confirmed_and_uncertain_results_only`, and
  `test_failed_composition_has_diagnostic_and_never_sends`.
- [ISSUE-009](../issues/ISSUE-009-whatsapp-composer.md).

# Consequences

This supersedes only ADR-0050's sole-message restriction; the separate composer,
template binding, transcript preservation and pre-send validation decisions remain.
Historical snapshots stay unchanged. Booking evidence may contain personal data and
uses existing scoped provider/evidence controls. No new model call or provider is added.
