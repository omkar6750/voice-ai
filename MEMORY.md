# Working state

Phase: RFC-0003 schema review implementation, execution safety and persistence slices.

Cleanup: removed old voice-agent CLI, duplicate config/pipeline/provider factory and
unused modem compatibility exports. Protected demo remains the only live-call entrypoint;
its settings, capture and telephony dependencies remain. DB configuration lives in
contracts/. PLAN-0003 now has an ordered remaining-work checklist and deletion inventory.

Completed: typed runtime configs, versioned agents/tools, integration vault/media catalog, mutable
pgvector knowledge, evidence models/spool, compact dashboard, and schema migration.

New: ADR-0006/0007 revision 2 updated in place at user request. Migration 0003 adds
JSONB conversion, publication/binding guards, draft concurrency and Run-owned evidence.
Clone-draft and browser request APIs added; browser requests do not start media transport.

Migration 0004 adds span-linked flow visits, ordered immutable tool results and typed
provider metrics. Finalized evidence now travels through spool, HTTP and PostgreSQL;
timeline includes results and visits. This path is not wired to the live call runner yet.
Credential validation/redaction, environment-backed vault loading and account-scoped
receipt matching are covered. Current full suite: 66 passed, two upstream deprecation warnings.
One old-default-config test was removed with the obsolete implementation.

New: migrations 0005-0010 add endpoint claim fencing, callback attempts, analysis history,
artifact metadata, operational ingestion-token naming and execution ownership guards.
Resolved snapshots include exact tool definitions, KB identities/names, logging/retention,
application/dependency identity and a canonical hash. Claimed snapshots are immutable.
Analysis and artifact APIs, explicit no-redial reconciliation, contact validation and
shared mutable-KB contracts are implemented. Runtime executor uses a call driver and
spool delivery; fake-driver API/database integration is tested. No native pipeline host
has been connected to that executor, so API queueing still does not place real calls.

New: executor streams durable evidence during calls, separately monitors writer health,
and stops execution on permanent ingestion/storage failure. Transient idempotent evidence
requests retry; external calls/actions never do. Cancellation waits for acknowledgement
writes before final drain. Spool creation/close failures now still reach driver cleanup
and incomplete terminal reporting when transport release is confirmed.

Next: native configurable Pipecat host and reviewed action adapters, provider OTel capture,
live tool/flow evidence, classifier/summarizer cadence, recording registration at cleanup,
automatic-callback polling, and ingestion job recovery. Keep legacy Call ownership columns
until compatibility readers migrate; DB guards now prevent disagreement with Run.
Validation: Alembic reports no schema drift; scoped Ruff, OpenAPI/TypeScript generation
and dashboard build pass. See PLAN-0003 for explicit remaining work.
Do not edit `scripts/demo_call.py`.

Validated demo is user-tested reference. Existing DB at 55432 is plain PostgreSQL;
isolated pgvector validation uses port 55433. Provider keys remain local-only.
