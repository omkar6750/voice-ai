# ADR-0021: Typed evidence and shared delivery finalization

Status: Accepted

## Context

Run `d9fa3955-c161-4de1-a9fd-ec55610188d4` had 12 exchanges and 23 messages in its
durable spool, while PostgreSQL held only 4 exchanges and 6 messages. A diagnostic
created for a rejected `change_node` transition carried both `timestamp_ns` (the
evidence event clock) and `occurred_at` (the progress-diagnostic envelope clock).
Strict `EvidenceBatch` validation failed in the runtime client before the API request;
the spool correctly kept the rejected batch unacknowledged. The normal call runner
reported incomplete evidence, but browser and Twilio finalizers could cancel delivery
and mark their runs complete without draining or reporting the spool.

The contract audit also found the STT observer using the non-contract output state
`missing_final_transcription`. The normalized `output_state` vocabulary already has
`failed`; the specific cause belongs in span attributes and diagnostic evidence.

## Decision

1. `EvidenceRecord` is the event contract from producer through persistence. A shared
   TypeAdapter validates the discriminated record before `ExchangeTracker` submits it
   and again before `DurableSpool` appends it. `EvidenceBatch` remains the shared batch
   contract for client serialization and API ingestion.
2. Diagnostic payload fields are shared between runtime and API schemas. Progress
   diagnostics keep their explicit `diagnostic_id`/`occurred_at` envelope. Evidence
   diagnostics keep their event ID and `timestamp_ns` envelope. The tracker adapts
   between them by discarding only the progress timestamp and preserving the stable
   diagnostic ID.
3. A producer-side validation failure latches spool health, prevents append, and stops
   execution through the existing health monitor. Already queued valid records are
   drained to disk before close where the writer remains healthy. Validation diagnostics
   expose only event kind and schema location, never rejected input values.
4. API event-to-row mapping is exhaustive. Messages and operation spans have explicit
   branches; a future event without a mapping raises rather than silently becoming a
   `TraceSpan`.
5. Runner, browser, and Twilio paths use shared uploader finalization: stop the uploader,
   flush, perform a final drain when safe, close the spool, and preserve unacknowledged
   data on failure. Active execution is supervised so a permanent evidence failure stops
   it safely. A completed call remains completed if only evidence finalization fails.
6. Evidence completeness is a separate nullable timeline field. `null` means no explicit
   completeness claim; `false` means incomplete; `true` means complete. The dashboard
   warns only for explicit incomplete state. Existing `Run.final_state` is sufficient;
   no migration is needed.
7. Recovery is an operator-run CLI, not direct database access or a new API. It defaults
   to read-only dry-run, validates the full pending suffix before writes, and supports
   only the known diagnostic `occurred_at` correction. Apply uses authenticated normal
   ingestion and advances the existing `.ack` cursor after each accepted batch. The
   original JSONL spool is unchanged.
8. Span output uses the existing normalized states. The missing-final-STT cause is stored
   in `attributes.failure_reason` and a separate diagnostic, not invented as another
   output-state enum value.

## Consequences

- Invalid producer records cannot become durable poison records. If validation fails,
  the call stops visibly instead of silently losing one event and continuing.
- Spool disk failures and evidence delivery failures share the finalization path while
  retaining their distinct exception causes and safe event coordinates.
- No schema migration is required. Timeline OpenAPI and generated TypeScript include
  `evidence_complete`.
- Historical runs without a stored completeness claim remain `null`; they are not
  retroactively asserted complete based only on their call status.
- The recovery CLI may replay already committed IDs safely because the ingestion API
  verifies idempotent identity. It does not repair any other malformed legacy payload.

## Verification

- Focused tests cover progress-to-evidence diagnostic adaptation, producer validation,
  spool non-append, sanitized validation coordinates, final drain and retained cursor,
  transient replay, permanent failure supervision, and STT output-state normalization.
- Integration coverage now constructs all evidence discriminants, posts/replays them,
  and asserts their expected database rows. The integration suite requires an isolated
  `VOICE_TEST_DATABASE_URL`; it was skipped when that environment was absent.
- OpenAPI was exported, dashboard types generated, and the production dashboard build
  passed.
- The affected run was replayed through the local authenticated API: 177 pending records
  were accepted; timeline counts are now 12 exchanges and 23 messages; the acknowledgement
  cursor is at the 296,259-byte spool end. A subsequent dry-run reports zero pending rows.

## Known limitations

- Physical browser/WebRTC and Twilio provider disconnect tests were not run in this
  environment; the shared delivery lifecycle and supervision helpers are covered with
  deterministic tests.
- A separate pre-existing uncommitted prompt-marker/native-flow change causes
  `test_native_node_compiles_marker_without_changing_saved_prompt` to fail: the current
  local implementation retains the leading `#` while that test expects it stripped.
  This workstream does not modify that unrelated in-progress agent change.
