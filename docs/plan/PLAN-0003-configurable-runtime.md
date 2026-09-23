# Configurable runtime implementation

Approved scope: RFC-0003, ADR-0006 and ADR-0007.

1. Expand schema non-destructively; typed configs and immutable publication.
2. Backend APIs, credential/media adapters and generated dashboard contracts.
3. Modular native runtime, exchange evidence and bounded spool.
4. Durable contacts, calls, callbacks and WhatsApp receipts.
5. Mutable hybrid knowledge search and context/cadence policies.

Validate migrations against isolated PostgreSQL, unit tests without live provider
calls, OpenAPI generation, dashboard build, Ruff and protected-demo hash.
Never dial a real contact during automated validation.

## RFC-0003 revision 2 implementation status

Started 2026-09-23. ADR-0006/0007 updated in place by explicit user request.

First slice implemented:
- Migration 0003 converts existing JSON to JSONB, adds creation defaults, FK indexes,
  publication/binding guards, same-agent published activation and Call run uniqueness.
- Published agent config is checked against exact relational tool/KB bindings.
- Binding and publication requests require expected revision. Draft cloning preserves
  configuration, lineage and bindings; parent lock serializes version allocation.
- Run owns exchange/message evidence; browser requests persist without a Call.
- Calls gain provider, external call ID, local correlation ID and provider metadata.
  Telephone requests generate correlation before dispatch; no call is dialed by API yet.
- Legacy Call/exchange columns remain during compatibility migration. Missing legacy
  Runs get explicitly incomplete envelopes, not fabricated historical runtime settings.
- Six opt-in PostgreSQL tests exercise direct SQL guards, clone behavior, two-connection
  edit races, stale binding publication, browser transcript ownership and JSONB/uniqueness.

Second slice implemented:

- Migration 0004 adds flow visits linked to timing spans, ordered tool results,
  immutable result payloads/consumption boundaries and typed provider metrics.
- Replay-safe evidence ingestion accepts finalized exchanges, messages and operation
  starts/ends. Runtime spool HTTP delivery only acknowledges successful ingestion.
- Timeline includes visits, delayed tool results, sanitized provider inputs/outputs,
  OTel IDs and optional latency/usage metrics. Unknown metrics remain null.
- Credential-bearing validation inputs are omitted from error responses; evidence is
  redacted before storage. Action adapters must still exclude decrypted secrets.
- Vault reads deployment settings and supports tested rotation/fail-closed behavior.
  WhatsApp receipts match account and phone identity, lock updates and deduplicate.
- Validation: 37 tests passed against isolated migrated PostgreSQL on port 55433;
  scoped Ruff checks passed; protected demo hash unchanged. No live calls made.

Remaining: complete model/migration constraint parity, additional same-run operation
relationships, remove duplicate legacy ownership once migrated, typed provider lifecycle
and audio validation, complete configuration resolution/hash, live Pipecat evidence
wiring, analysis/fact records, callback claims/recovery, mutable-KB contract unification,
parallel receipt-race tests, artifact retention and runtime dispatch.
Do not treat schema fields or queued browser requests as working browser/cloud calling.

Legacy published rows without publication timestamp are preserved. NOT VALID checks
enforce new writes without inventing old timestamps; audit/validate old rows explicitly.
