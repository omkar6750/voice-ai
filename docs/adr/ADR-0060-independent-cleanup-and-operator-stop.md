---
id: ADR-0060
title: Independent cleanup delivery and ordered operator stop
status: Accepted
version: 1
date: 2026-10-15
authored_by: codex
session: documentation-review-20261015
supersedes: null
superseded_by: null
related: [ADR-0044, ADR-0055, ADR-0056, ADR-0057, ADR-0059]
---

# Context

This is a retrospective record of the user-authorized behavior implemented in
`42f7b10` on October 10. It extracts the cleanup portion of ADR-0059's amendment;
it introduces no new runtime policy and does not supersede telephony attribution.

An evidence conflict could prevent release reporting. Dashboard stop could disable
modem audio before queued PCM writes stopped, producing a misleading pipeline error.
Lease expiration alone could not prove the old worker or modem had released ownership.

# Decision

Lifecycle-only synchronization can report confirmed cleanup independently of
transcript/evidence ingestion. Rejected evidence remains in the spool and its
incompleteness is explicit. Do not weaken immutable evidence validation.

Stop requests are idempotent and fence queued/preparing execution. An active stop
retains ownership until cleanup is verified. SIM7600 cleanup cancels and awaits
pipeline workers before modem hangup/audio disable. Failed pipeline shutdown still
attempts physical cleanup and closes ports; it cannot claim full release merely
because a modem command succeeded.

Pipeline, media/controller and artifact handling use bounded independent cleanup
attempts. Storage failure does not invalidate already confirmed transport release.
Run, Call, dispatched Callback and assignment updates follow the cleanup result.
Lease expiry, evidence rejection, duration limits, operator cancellation and pipeline
failure remain distinct facts. Historical runs are not automatically relabeled.

# Evidence

- [Driver ordering](../../packages/voice_runtime/voice_runtime/telephony/driver.py).
- [Session cleanup](../../apps/runtime/voice_runner/session.py) and
  [runtime ingestion](../../apps/api/voice_api/api/v1/endpoints/runtime.py).
- [Operator-stop regressions](../../tests/unit/test_run_stop.py),
  [PCM shutdown ordering](../../tests/unit/test_sim7600_release_verification.py), and
  [cleanup synchronization](../../tests/unit/test_runtime_cleanup_sync.py).
- [ISSUE-001](../issues/ISSUE-001-operator-stop.md) and
  [ISSUE-004](../issues/ISSUE-004-cleanup-and-leases.md).

# Consequences

An uncertain owner remains reserved until verified recovery. Independent cleanup
delivery reduces ambiguity without fabricating missing evidence. Unit tests prove
ordering and state transitions under controlled failures; fresh hardware acceptance
is still required after deploying or restarting a changed runtime.
