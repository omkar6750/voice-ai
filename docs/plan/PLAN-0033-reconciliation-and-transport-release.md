---
id: PLAN-0033
title: Fact-based run reconciliation and transport release
status: Proposed
date: 2026-09-28
related: [PLAN-0013, PLAN-0030, PLAN-0031, RFC-0011, ADR-0013, ADR-0017, ADR-0021]
---

# Fact-based run reconciliation and transport release

## Decision

Reconciliation must repair ownership and record verified facts; it must not
guess the historical call outcome. Keep the existing safety rule that stale or
uncertain execution cannot automatically redial.

Separate these dimensions:

- run lifecycle: queued, claimed, running, completed, failed, uncertain;
- worker lease: owned, expired, released, unknown;
- transport: active, idle, release requested, unknown;
- call outcome: the semantic result from PLAN-0031;
- evidence: complete, incomplete, or unknown;
- reconciliation: not required, required, verified, or disputed.

The existing `/runs/{run_id}/reconcile` endpoint currently changes every
uncertain run to `failed`. That is safe for preventing redial, but it loses the
distinction between “worker is now safely stopped” and “we know why the remote
call ended”. The new endpoint should keep the run non-redialable while storing
those facts independently.

## Current safety boundary

The runner claims an endpoint with a token and heartbeat, refuses a second claim
after dispatch, closes the driver before final progress, and refuses to release
the endpoint when cleanup fails. The API rejects stale tokens and active/expired
execution. Reconciliation requires operator confirmation that the worker
stopped and transport is idle.

Do not weaken these protections. Extract the state decisions into a service so
`execution.py`, `reconciliation.py`, runner finalization, browser sessions,
and Twilio execution do not implement competing transitions.

## Proposed service seam

Add a small application service such as
`voice_api.services.reconciliation_service` with operations:

```python
async def mark_worker_expired(run_id, observed_at, source) -> None: ...
async def record_transport_observation(run_id, observation) -> None: ...
async def reconcile_uncertain_run(run_id, verified_facts, note) -> ReconciliationResult: ...
```

The service must:

- lock the run and endpoint in one transaction;
- validate the claim token/fencing state where applicable;
- refuse reconciliation unless worker stopped and transport idle are both
  explicitly verified;
- preserve the original uncertain outcome and diagnostics;
- record who, when, how, and what was observed;
- release the endpoint only after verified facts are persisted;
- make repeat reconciliation idempotent for the same facts;
- reject contradictory later facts instead of overwriting history.

## Data model

Prefer additive fields/tables over encoding everything into `final_state`:

`Run` should retain its operational `status`, while a reconciliation record
stores:

- run ID and endpoint ID;
- worker token/fencing token hash, not the raw token;
- worker state and observed timestamp;
- transport provider and observed transport state;
- modem/Twilio/browser observation metadata, redacted;
- `transport_idle_verified` and `worker_stopped_verified`;
- resulting endpoint state;
- operator identity, note, and source;
- created-at and superseded-by relationships if a later provider callback
  changes the interpretation.

Do not rewrite the original final evidence. Add an audit event and expose the
latest derived reconciliation state in the run response.

## State transitions

Allowed transitions should be explicit:

```text
claimed/running + lease expires
    -> uncertain + endpoint retained + reconciliation required

uncertain + worker stopped + transport idle verified
    -> failed/transport_released + reconciliation verified

uncertain + either fact missing
    -> uncertain + endpoint retained

uncertain + contradictory active transport observation
    -> uncertain + reconciliation disputed
```

The operator may close the ownership incident after verified release, but may
not upgrade an uncertain call to successful completion without authoritative
provider/transport evidence. A later Twilio callback or modem observation may
add evidence through a separate idempotent observation path; it must not erase
the prior uncertainty record.

## API and dashboard

Keep the existing reconcile endpoint for compatibility, but extend its response
with:

- `run_status`;
- `outcome_code`;
- `transport_state`;
- `reconciliation_state`;
- `evidence_complete`;
- `redial_allowed: false`.

Add a read endpoint for reconciliation history before adding mutation controls
to the dashboard. The UI should show the blocking fact, last heartbeat, last
transport observation, evidence completeness, and the exact confirmation an
operator is making. Never label an uncertain remote call “completed” merely
because the local worker stopped.

## Implementation order

1. Add typed reconciliation contracts and transition tests.
2. Add reconciliation audit persistence and migration.
3. Move current endpoint-lock logic into the reconciliation service without
   changing behavior.
4. Make runner, browser, and Twilio finalizers write observations through the
   service.
5. Extend the existing reconcile response and run detail API.
6. Add read-only dashboard history and explicit operator confirmation later.
7. Only after this is stable, consider provider-specific automatic observation
   callbacks; never add automatic redial.

## Tests

- expired lease becomes uncertain and keeps endpoint occupied;
- stale token cannot mutate the run;
- reconciliation without both verified facts is rejected;
- successful reconciliation is idempotent;
- repeated conflicting reconciliation is rejected and audited;
- concurrent claim and reconcile serialize correctly;
- transport cleanup failure remains uncertain;
- evidence failure remains separate from transport state;
- Twilio callback after reconciliation is idempotent and does not erase audit;
- modem idle observation is stored without inferring cause from RSSI;
- browser disconnect is recorded as observation, not automatically as success;
- no reconciliation path can trigger a dial or redial.

## Non-goals

- No automatic redial.
- No speculative “completed” result for an uncertain remote call.
- No direct database updates from provider adapters.
- No replacement of the evidence spool/replay system.
- No dashboard WebSocket implementation before the Clerk worktree is ready.

## Acceptance criteria

- Endpoint ownership and call outcome are independently explainable.
- Every reconciliation action is auditable and idempotent.
- Uncertain calls remain visibly uncertain until verified facts exist.
- The existing fencing and no-redial protections remain intact.
- Runner, browser, Twilio, and modem paths share one reconciliation seam.
