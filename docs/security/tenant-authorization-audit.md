# Tenant authorization audit

Reviewed 2026-09-29 against the Clerk/main integration. This is a code and
isolated-database audit, not evidence of live production acceptance.

| Surface | Reviewed boundary |
| --- | --- |
| Customer resources | Clerk session, registered active org, current membership/local disabled-user check; bound request session; explicit member-read markers, otherwise admin. |
| Org catalog/invitations/ownership | Actor/path membership checked independently of active-org claim; admin/owner checks, owner/last-admin safeguards. |
| Platform access | DB singleton assignment and explicit audited expiring support session, not email/env/frontend privilege; recordings exclude support mode. |
| Runtime mutations | Backend service token, per-run token for run-addressed writes; persisted run supplies org before evidence/artifact/progress writes. |
| WhatsApp callbacks | Scalar stored connection ownership bootstrap, tenant binding then challenge/signature verification before processing. |
| Twilio callbacks/media | Stored correlation ownership, canonical configured public URL/signature, account/call identity and fenced media claim. |
| Calendar OAuth | High-entropy state hash supplies org; expiry/PKCE; server-only tokens. |
| Browser media | Exact origin, short-lived one-use ticket, persisted same-org session/run; issuing-actor revocation at handshake belongs to the hosted slice. |
| Knowledge background ingestion | Source org bootstrap in each fresh session, fenced build tokens, same-org relations; deleted source no-op. |
| Raw SQL/Core/bulk ORM | No scope fails closed; ORM filters/stamps; raw retrieval explicit matching org predicates; unsafe statements rejected. |
| JSON/non-FK references | Scoped publication/resolution checks pinned tool/knowledge/calendar IDs; credential slice adds provider/purpose bindings without modifying published JSON. |
| Relational references | Required org columns, PostgreSQL same-org reference triggers and session identity-map/reassignment safeguards. |

`test_route_authorization_inventory.py` requires auth/scope dependencies on
all HTTP routes except exact reviewed signature/state callbacks and inventories
the two media WebSockets. It does not replace callback/business-capability tests.

## Findings and follow-through

- Main's hard config cleanup disables triggers with session_replication_role.
  It is now explicitly development-only, rejecting hosted requests before DB access.
- Call/contact cascading cleanup must not discard metadata for retained/pending
  Cloudinary recordings. Recording slice supplies deletion preconditions;
  bulk recording deletion retains calls/transcripts.
- Browser handshake must recheck ticket actor membership before loading keys.
- Hosted profile must deny physical SIM inventory/probes and provider env fallback.

## Migration and validation evidence

Both histories reach0040_merge_clerk_and_runtime. The Clerk-side0038 disposable
clone upgraded previously. A fresh main-side voice_main_rehearsal_20260929 clone
was copied from main0029 on port55432; only the clone received Clerk catalog,
previously verified rehearsal identity mapping and backfill. Upgrade and
Alembic metadata parity passed.605 PostgreSQL-enabled tests and Ruff passed;
11 new route/cleanup regressions passed. Dashboard build passed with the
existing entry-chunk size warning. Original main/Clerk databases were not migrated.

New credential/recording migrations require separate rehearsal on both clones.
Live identity proof, backups, signed-in two-user/two-org invitation/removal probes,
and audible hosted calls remain acceptance gates. Local results do not prove
Render capacity or authorize implicit migration of an existing database.
