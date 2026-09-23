# Working state

Phase: RFC-0003 schema review implementation, integrity and evidence slices.

Completed: typed runtime configs, versioned agents/tools, integration vault/media catalog, mutable
pgvector knowledge, evidence models/spool, compact dashboard, and schema migration.

New: ADR-0006/0007 revision 2 updated in place at user request. Migration 0003 adds
JSONB conversion, publication/binding guards, draft concurrency and Run-owned evidence.
Clone-draft and browser request APIs added; browser requests do not start media transport.

Migration 0004 adds span-linked flow visits, ordered immutable tool results and typed
provider metrics. Finalized evidence now travels through spool, HTTP and PostgreSQL;
timeline includes results and visits. This path is not wired to the live call runner yet.
Credential validation/redaction, environment-backed vault loading and account-scoped
receipt matching are covered. Full suite: 37 passed, two upstream deprecation warnings.

Next: finish model/constraint parity and provider-neutral ownership, resolved snapshots,
analysis/callback safety, mutable-KB contract unification and modular runtime dispatch.
See PLAN-0003 for explicit remaining work. Do not edit `scripts/demo_call.py`.

Validated demo is user-tested reference. Existing DB at 55432 is plain PostgreSQL;
isolated pgvector validation uses port 55433. Provider keys remain local-only.
