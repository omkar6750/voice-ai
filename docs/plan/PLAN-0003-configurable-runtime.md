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

Third slice implemented:

Validation: 55 tests passed; Ruff and dashboard build pass; OpenAPI/TypeScript regenerate.
Protected demo hash remains `3fe545de555fbb40bdfa187031b67484ebf87199`.

- Migrations 0005-0010 preserve existing IDs/data, align ORM indexes and legacy nullable
  timestamps, and enforce cross-run span/tool ownership. `alembic check` reports no new
  upgrade operations. This is schema-diff evidence, not proof of every runtime guarantee.
- Resolved snapshots retain exact tool definitions/bindings, KB identity/name, effective
  logging/retention, application revision/dirty flag and dependency versions. Canonical
  SHA-256 identifies configuration. Endpoint config is pinned at claim; claimed snapshots
  cannot change. Historical snapshots lacking these facts remain unchanged.
- Contact phones normalize explicit international format; timezone validates against IANA
  data. `tzdata` is installed for Windows. Missing timezone remains unknown.
- Callback scheduling is replay-safe; launch locks the row and pins one call. Automatic
  launch respects off-by-default workspace settings, due window and one-attempt limit.
  A polling scheduler is not running yet. Missed windows require manual launch.
- Endpoint claims serialize concurrent workers, validate PCM rates and renew leases.
  Expired work becomes uncertain and reserves the modem. Explicit reconciliation requires
  operator confirmation that worker stopped and modem is idle; it never redials or invents
  a successful outcome/hangup timestamp. Actual dispatch remains a separate process step.
- Runtime executor fences before side effects, closes transport before terminal reporting,
  delivers finalized evidence, and reports incomplete delivery. Fake drivers exercise the
  full API/database path. SIM7600 driver wraps the tested session, but its configurable
  Pipecat host remains to be implemented. No hardware/provider calls run in tests.
- Append-only classification/summary/contact-fact evidence validates source messages,
  operation outcomes and supersession. Summary-prefix application preserves newer messages
  and complete tool pairs. Neither module is wired to live classifier cadence yet.
- Artifact APIs register finalized WAV/debug files, inspect audio/checksum metadata, enforce
  per-call logging policy and expire only registered files. Safe relative paths reject
  traversal/links. Reusable integration media is excluded. Runtime registration is pending.
- KB APIs share runtime contracts. Agent/request retrieval settings own weighted RRF,
  thresholds/budget/timeout. Fractional SQL weight typing is fixed. Ingestion settings own
  chunking, Markdown handling and 768-dimensional embeddings. Existing legacy KB retrieval
  JSON is preserved but ignored by search. Explicit rebuild fences stale jobs and preserves
  active chunks on failure; source deletion removes chunks. No KB history added.
- Embedding adapter client lifetime is fixed. Request shape checked against the
  [official Gemini embeddings API](https://ai.google.dev/api/embeddings).
- OpenAPI export and frontend contract generation work; dashboard build remains valid.
  Operator token is now memory-only. No dashboard redesign performed.

Remaining: native configurable Pipecat host, provider OTel capture, reviewed action execution
and live tool/flow links, cadence integration, automatic callback polling, recording/log
registration from runtime, durable ingestion-job recovery, parallel WhatsApp receipt tests,
and migration of compatibility readers before removing duplicate legacy Call columns.
HTTP tool egress controls and full model-setting capability validation also remain pending.
Do not treat schema fields or queued browser requests as working browser/cloud calling.

Legacy published rows without publication timestamp are preserved. NOT VALID checks
enforce new writes without inventing old timestamps; audit/validate old rows explicitly.

## Live evidence delivery slice

Implemented continuous background upload from the durable spool while the driver runs.
Independent health checks detect writer/quota failures even during blocked HTTP requests.
Only replay-safe evidence retries transport errors, HTTP 429 and server errors; permanent
rejections stop execution, retain unacknowledged records and mark evidence incomplete.
No call or action retry policy changed.

Cleanup stops the uploader before final drain. Cancellation waits for a cursor write
already in progress, preventing a late acknowledgement from racing that drain. Spool
creation/close failures no longer bypass driver cleanup or terminal failure reporting
when transport release is confirmed. Uncertain cleanup still reserves the endpoint.

Validation: 67 tests pass against isolated PostgreSQL, scoped Ruff and diff checks pass,
protected demo hash unchanged. Added 12 offline cases covering pre-hangup upload,
cancellation, transient replay, permanent rejection, storage failures and cursor races.
Older integration assertions now count only their own run's rows, allowing existing
validation data without deleting it. Two upstream deprecation warnings remain.

Native Pipecat host, actual provider/tool capture, recording registration and the other
remaining items above are still pending. This slice does not place live calls.
