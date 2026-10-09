# Production configuration sync · 2026-10-04

Target: Supabase `voice-ai-production` (`nhvytmqzhbgadgrlbvat`), Singapore.
This is the hosted application database; earlier Neon references in deployment
planning were assumptions and do not describe the current database.

## Completed

- Verified the initial Alembic revision was `0043_remote_artifact_guard`.
- Applied repository migrations 0044–0047 through the Supabase migration connector.
  The runs index was created normally inside the migration transaction rather than
  concurrently: the destination had one run, and the resulting index definition
  is identical. No run or configuration records were deleted or replaced.
- Verified `alembic_version` is `0047_dashboard_read_index`.
- Enabled RLS and revoked `anon`/`authenticated` access on the five new runtime/chat
  tables. They are API-owned tables, with no direct-client policies.
- Verified the destination still has one run and zero chat conversations.

## Configuration transfer completed

After both local Docker databases started, compared PostgreSQL on ports 55432
(main checkout) and 55433 (flow improvements worktree). The current Ritu agent
was in the worktree database: published version 6, revision 54, version ID
`8a5274df-319b-41a0-b3f1-a068828f89fa`.

Imported a standalone snapshot of that version, its six tool bindings and one
knowledge binding, four missing published tool versions, one missing tool,
one knowledge base/source with six chunks, the required calendar integration
and encrypted tokens, one missing integration media record, one missing provider
credential, and three contacts (two updated and one inserted).

Local revision ancestry that was absent from production was omitted from the
snapshot's `parent_id` metadata. Prompts, configuration, version numbers and
revisions match the source. Existing published versions were not modified.
An initial broader transaction was rejected by automatic approval review and
did not execute; the completed transaction had no binding deletions and imported
only the current Ritu configuration and required dependencies.

The local and destination organizations share the same Clerk organization but
have different database IDs. Preserved the destination organization and owner;
mapped imported rows to it and encrypted new secrets with its scoped AAD.
Existing required credentials had matching plaintext and retained their existing
encrypted envelopes. All seven required provider credentials and all four
destination calendar secrets passed decryption verification using the local
vault keys, which also decrypt the pre-existing destination secrets. The current
Render environment's vault keys and live provider calls have not been verified.

Verified final totals: four agents, 16 agent versions, 11 tools, 15 tool versions,
93 tool bindings, three contacts, eight provider credentials, one integration
connection, two calendar integrations, three knowledge bases/sources and 15
knowledge chunks. Ownership and workspace settings were preserved. The imported
published agent does not configure the new composer; no composer settings or
agent prompts were invented during this transfer.

No runs, calls, chat history, evidence, callbacks, temporary grants, leases or
runtime assignments were imported. Production remains at one existing run and
zero chat conversations. Migration revision remains `0047_dashboard_read_index`.

## API database permissions: repair completed

The deployed API connects through Supavisor as `voice_app`, which owns the older
application tables. The five new tables created through the management migration
are owned by `postgres`. `voice_app` has no SELECT/INSERT/UPDATE/DELETE grants on
them and does not bypass RLS; there are currently no RLS policies on them.

This explains the GET `/api/v1/runs` failure in
`recover_expired_assignments`: it reads `runtime_assignments` before listing runs.
The table and all expected columns exist, and the schema is at revision 0047.
The migration's assumption that the API was using the table-owner role was wrong.
Chat and runtime writes would also be affected by the missing access.

Applied `supabase-runtime-chat-permissions.sql` to grant the existing server-only
`voice_app` login CRUD and role-specific policies on these five tables. It does
not grant browser roles access or change Clerk/app ownership. Automatic approval
review initially rejected this repair as a broad permission expansion. The user
then explicitly approved it, and Supabase migration
`voice_api_runtime_chat_server_permissions` completed successfully.
Verified all five tables grant SELECT/INSERT/UPDATE/DELETE to `voice_app`, retain
RLS, and have a FOR ALL policy restricted to that role. `anon` and `authenticated`
still cannot select these tables. Alembic revision remains 0047. No API redeploy
is needed for database grants; an authenticated dashboard retry is still required
to verify the complete HTTP request path.
