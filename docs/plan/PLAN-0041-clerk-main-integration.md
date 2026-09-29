# PLAN-0041 · Clerk and main integration

Status: Integration verified locally; user authorized merge; production acceptance open.

## Scope and merge policy

Merge `codex/clerk-integration` into a branch based on main `c700103`, without
rebasing or changing either source checkout. Preserve main's Twilio lifecycle,
callback-role routing, typed evidence, classifier cadence and removal of unused
wait settings. Preserve Clerk's organization-only tenancy, standard admin/member
roles, server-side authorization, organization creation and starter provisioning,
org home route, and WebSocket browser tests. The protected demo is unchanged.

Clerk ADRs were renumbered to ADR-0028 through ADR-0031 and Clerk plans to
PLAN-0037 through PLAN-0040 to avoid collisions with main's runtime documents.
PLAN-0040 and ADR-0031 remain the authoritative organization design.

## Integration fixes

- Join both Alembic heads at `0040_merge_clerk_and_runtime`. Preserve the full
  classifier rewrite, approved for verification only on isolated databases.
  Scope delayed run context events, including their database ownership trigger.
- Make overlapping schema-alignment migrations compatible with both histories.
- Bind run ownership for native WhatsApp lookup, asynchronous outcome persistence,
  delivery, consumption and cleanup, callback tools, knowledge, and Twilio outcomes.
- Use per-run service tokens for Twilio evidence/artifacts; do not use operator
  credentials for runtime delivery. Do not fall back to environment provider keys
  after per-organization settings have been resolved.
- Preserve browser termination truth, bounded cleanup and artifact failure
  reporting while using Clerk's WebSocket transport.
- Make evidence delivery replay idempotent after consumption; retain strict
  verification of immutable delivery fields. Keep raw exception bodies out of
  persisted runner failure messages.
- Carry Clerk/support authentication into binary media and artifact requests;
  hide media mutation controls from members. Regenerate dashboard API types.

## Verification

Use disposable PostgreSQL clones only. The original Clerk and main databases
are not migration targets. Verified upgrade from the Clerk-side 0038 clone to
the merged head and Alembic metadata parity. A stale local-media path was cleared
only in the disposable clone after confirming its file was absent.

Run the complete Python suite with `VOICE_TEST_DATABASE_URL` set to the migrated
clone, Ruff, dashboard API generation, and the dashboard production build. The
native context regression exercises real PostgreSQL ownership plus asynchronous
result delivery/consumption. Existing tests cover Twilio, browser shutdown,
fenced execution, org authorization and negative cross-org requests.

Final integration verification on 2026-09-29: 605 tests passed with PostgreSQL
enabled; Ruff passed; Alembic reports one head and no new upgrade operations;
the dashboard production build passed. Its organization page now has a separate
lazy chunk; the entry bundle still exceeds Vite's warning threshold. Python
reports upstream deprecation warnings and asyncpg cancellation-coroutine
warnings during test-session teardown; these are not counted as test failures.

## Remaining acceptance and rollout

- Code-level customer-route/raw-SQL/non-FK/background-job audit is recorded in
  `docs/security/tenant-authorization-audit.md`. Hosted follow-through is tracked
  in PLAN-0042; passing tests do not prove every production access path.
- Perform signed-in two-user/two-org invitation acceptance, switching, and
  cross-org negative probes, plus an actual provider/hardware voice call.
  Browser automation remains prohibited by the working agreement.
- Main-head upgrade/backfill rehearsal passed on a fresh disposable clone;
  Alembic parity and605 tests passed. Reverify live identities, take a backup and
  inspect classifier rewrites before any live upgrade.
- Organization creation is implemented and enabled by the application default
  and example configuration. Production must explicitly decide the flag after
  the above gates; live Clerk instance settings are a separate external check.
- PLAN-0042 chooses Netlify dashboard, Render API/Pipecat, Neon PostgreSQL,
  authenticated Cloudinary recordings and private Supabase documents/diagnostics.
  No cloud resources are provisioned by the foundation merge.
- Resolve the existing dashboard large-bundle warning before optimizing launch
  performance; it does not prevent the production build.

The user authorized the foundation merge after local verification. Live deployment
remains gated by the checks above; this is not a production-ready claim or
authorization to mutate live data.
