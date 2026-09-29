# Handoff 005: run and endpoint reconciliation

## Objective

Define the operator workflow and data model for uncertain calls, stale endpoint
claims, dead workers, modem disconnects, Twilio status disagreement, and
verified transport release.

## Current implementation

API routes:

- `apps/api/voice_api/api/v1/endpoints/reconciliation.py`
- `apps/api/voice_api/api/v1/endpoints/execution.py`
- `apps/api/voice_api/api/v1/endpoints/telephony.py`
- `apps/api/voice_api/api/v1/endpoints/browser_sessions.py`

Runtime:

- `packages/voice_runtime/voice_runtime/execution/runner.py`
- `packages/voice_runtime/voice_runtime/telephony/sim7600.py`
- `packages/voice_runtime/voice_runtime/telephony/status.py`
- `packages/voice_runtime/voice_runtime/telephony/twilio.py`

The runner claims a run, renews ownership, closes the driver, drains evidence,
and reports progress. It deliberately refuses automatic redial. Endpoint
recovery requires verified transport release. The API has reconciliation
support, but the dashboard has no dedicated reconciliation route.

Relevant safety behavior includes:

```python
if claim["status"] != "claimed":
    raise RuntimeError("Execution already started; refusing repeat dial")
```

and endpoint recovery guards that reject active or uncertain calls.

## Questions for the research agent

The research agent has no repository access, so the following existing project
constraints are summarized here rather than delegated for lookup: execution is
fenced by a claim and heartbeat; automatic redial is intentionally refused;
endpoint recovery must prove transport release; diagnostics and evidence must
be typed and auditable; and uncertain calls must not be silently marked
successful. The implementation agent can later compare the recommendation with
RFC-0011, ADR-0013, ADR-0017, ADR-0021, and PLAN-0030.

## Web-research instructions

Search official documentation for distributed-worker leases and heartbeats,
fencing tokens, idempotent retries, Twilio call status/callback ordering,
SIM7600 or modem hangup/release behavior, and browser/WebRTC disconnect
semantics. Use public engineering sources only when official documentation does
not cover failure ordering. This is a design research task; do not assume any
specific database or queue product beyond the state and safety constraints
described above.

Determine:

1. Which run, call, endpoint, worker, modem, and Twilio states are authoritative
   when they disagree.
2. What evidence proves a worker stopped and a transport is idle.
3. Which operations are safe to retry, reconcile, or permanently refuse.
4. How long claims/heartbeats may remain stale before operator action.
5. What the reconciliation UI must show and which actions require confirmation.
6. Whether reconciliation should be read-only by default and how every action
   becomes auditable evidence.

## Required deliverable

Return:

- a state matrix across Run, Call, endpoint, worker, modem, browser, and Twilio;
- safe recovery and refusal rules;
- diagnostic codes and evidence records;
- API/dashboard route requirements;
- concurrency and fencing tests;
- manual verification procedures for SIM7600 and Twilio.

Do not add automatic redial.
Include source links, distinguish transport facts from proposed operator
policy, and call out which decisions require hardware/provider integration tests.
