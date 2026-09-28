---
id: PLAN-0030
title: Runtime evidence integrity, delivery lifecycle, and spool recovery
status: Implemented
date: 2026-09-28
related: [ADR-0007, RFC-0003]
---

# Runtime evidence integrity, delivery lifecycle, and spool recovery

## Existing repository facts

- Runtime records already use a discriminated Pydantic `EvidenceRecord` union at the
  HTTP client and API ingestion boundary, but `ExchangeTracker` and `DurableSpool`
  previously admitted generic mappings without validation.
- Progress diagnostics have `diagnostic_id` and `occurred_at`; evidence diagnostics
  have `id`, `diagnostic_id`, and `timestamp_ns`. A progress diagnostic was forwarded
  unchanged as evidence, so local batch validation failed before HTTP submission.
- `store_record` has explicit handlers for most evidence variants but ended with a
  generic fallback capable of mapping an unhandled event as a trace span.
- The normal runner drains evidence and records `evidence_incomplete`; browser and
  Twilio workers stopped the uploader and completed their runs without a final drain.
- Run outcomes and evidence completeness are distinct facts. Browser and Twilio runs
  may not have endpoint-claim progress tracking, so they persist their own final state.
- The affected run retains a JSONL spool and acknowledgement cursor. Recovery must use
  authenticated, idempotent evidence ingestion and must not alter the source spool.

## Exact scope

1. Validate each event against the shared discriminated event union before tracker
   submission and spool append. Adapt progress diagnostic envelopes into the evidence
   envelope without changing the event ID or timestamp_ns contract.
2. Reuse shared diagnostic payload contracts between runtime and API. Keep the
   progress and evidence event envelopes explicitly distinct.
3. Report permanent local validation failures using sanitized event index, kind, and
   validation path; do not include transcript/provider input values in errors.
4. Make database event dispatch exhaustive: every evidence variant is handled
   explicitly or fails loudly; no unknown-event-to-span fallback.
5. Share uploader supervision and final drain behavior across runner, browser, and
   Twilio execution. Preserve call outcome while storing evidence completeness
   separately and showing incomplete evidence in the run dashboard.
6. Add a run-scoped recovery CLI whose default is dry-run. It validates all pending
   records before writes, applies only the known diagnostic `occurred_at` correction,
   replays via the API, and advances `.ack` only after each confirmed commit.
7. Dry-run and, if the configured API is available, replay the retained affected run;
   verify timeline counts against the spool.

## Subsystems and files

- Runtime contracts and production: `contracts/evidence.py`, `contracts/diagnostics.py`,
  `execution/exchange.py`, `execution/spool.py`, `execution/evidence_client.py`.
- Delivery lifecycle: `execution/delivery.py`, `execution/runner.py`, API browser-session
  service, and Twilio execution endpoint.
- API storage/response: evidence endpoint, run timeline schema and endpoint, diagnostic
  schema reuse.
- Operator UI: generated OpenAPI contract and run detail completeness indicator.
- Recovery: `scripts/recover_evidence.py` and focused recovery tests.

## Public API and type changes

- Timeline `run` adds nullable `evidence_complete`. `null` means no finalized
  completeness claim exists; `false` is explicit incomplete evidence; `true` is complete.
- Regenerate `data/openapi.json` and dashboard TypeScript through the documented flow.
- No new write endpoint is added; recovery uses the existing authenticated evidence API.

## Database changes

- No migration: Run.final_state and RunDiagnostic already persist the needed state.
- Each successful evidence batch remains transactionally/idempotently persisted before
  spool acknowledgement. The recovery tool never writes PostgreSQL directly.

## Runtime behavior

- Typed event validation occurs before durable spool admission; invalid records do not
  append and do not poison an otherwise healthy spool writer.
- Diagnostic progress fields are explicitly adapted: `occurred_at` is removed from the
  evidence payload, `diagnostic_id` is retained, and the evidence envelope supplies
  `timestamp_ns`.
- Delivery failure while execution is active cancels/ends the active execution safely.
  Finalization stops the uploader, flushes, drains if safe, closes the spool, and retains
  all unacknowledged records on failure.
- Final call status represents call execution, not evidence delivery. Run final state
  separately records `evidence_incomplete`; a sanitized diagnostic records failure
  details and safe validation coordinates.
- Recovery dry-run is read-only. Apply posts validated batches and atomically advances
  the cursor only after API confirmation. Original JSONL bytes remain unchanged.

## Frontend behavior

- Run timeline displays an explicit incomplete/replay-required badge only when the API
  reports `evidence_complete: false`; unknown stays unasserted.
- No local duplicate Timeline DTO is added for the new field; OpenAPI-generated types
  are authoritative.

## Tests

- Diagnostic producer adaptation and strict evidence record validation before sink/spool.
- Full preservation of stable diagnostic IDs and timestamp_ns; no progress-only field in
  evidence.
- Invalid legacy records fail locally with safe location metadata and no HTTP request.
- Recovery normalization modifies only the known diagnostic progress timestamp.
- Final drain preserves cursor on failure and returns explicit diagnostic metadata.
- Delivery failure stops active execution; completed operation wins a simultaneous
  completion race and evidence failure is reported separately.
- Existing end-to-end evidence ingestion/replay tests verify API idempotency and storage.
- Focused Ruff, tests, OpenAPI export, dashboard generation/build.

## Acceptance criteria

- No producer-created event can enter the spool unless it validates as `EvidenceRecord`.
- `occurred_at` cannot poison evidence batches; progress diagnostics still retain it.
- Every event union branch has explicit database mapping behavior.
- All three live execution paths share supervised delivery and final-drain logic.
- Evidence failure is visible without relabeling an otherwise completed call as failed.
- Recovery dry-run reports exact pending count, event counts and corrections without
  changing spool/cursor/database; apply is idempotent and acknowledges only persisted
  batches.

## Manual verification

1. Run `uv run python scripts/recover_evidence.py --run-id <run-id>` and inspect the
   dry-run report; verify no spool/cursor/database changes.
2. Confirm the running API is pointed at the intended dev database, then run the same
   command with `--apply`.
3. Confirm the report shows 12 exchanges and 23 messages for the affected run, the
   cursor reaches the spool size, and dashboard timeline matches.
4. Simulate a permanent evidence API rejection during browser and Twilio sessions;
   confirm execution cleanup, visible diagnostic, replay-required UI state, and retained
   unacknowledged spool records.
5. Confirm a completed call with an evidence finalization issue retains completed call
   status while its timeline shows incomplete evidence.

## Explicit non-goals

- Do not edit `scripts/demo_call.py` or legacy seed data.
- Do not add an event-sourcing table, a new evidence API, alternate storage, or a second
  versioned evidence schema.
- Do not repair arbitrary historical spool schema drift; only the documented diagnostic
  `occurred_at` mismatch is eligible for automated recovery.
- Do not discard, rewrite, or synthesize missing evidence records.
- Do not mark a call failed solely because evidence finalization failed after successful
  call completion.

## Completion and verification results

- Runtime, browser, and Twilio paths now share evidence supervision/finalization; strict
  producer and spool validation, safe validation coordinates, and exhaustive API event
  mapping are implemented.
- The additional audit found and corrected the invalid STT `output_state`; its specific
  reason remains in span attributes and a diagnostic.
- A full event-discriminant API/database round-trip and idempotent replay integration test
  was added. It is skipped unless an isolated `VOICE_TEST_DATABASE_URL` is configured.
- Affected-run dry-run found 177 pending records and one diagnostic envelope correction.
  Apply replayed all 177 through the local authenticated API, yielding 12 exchanges and
  23 messages. The source JSONL remains intact; `.ack` equals the 296,259-byte file size;
  a subsequent dry-run found zero pending records.
- Focused evidence/runtime tests: passed; isolated-database tests skipped without the
  dedicated test DB. Repository Ruff passed. OpenAPI export, dashboard type generation,
  and production build passed.
- Full suite: 160 passed, 33 skipped, 1 failed. The remaining failure is the unrelated
  pre-existing uncommitted prompt-marker/native-flow mismatch documented in ADR-0021.
- No physical SIM7600/WebRTC/Twilio exercise was available; use the manual steps above.
