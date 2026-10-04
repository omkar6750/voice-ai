# Local ownership with Clerk basic roles

Status: application cutover in progress. No Clerk or database mutations performed.
Date: 2026-10-04

## Recommendation

Keep Clerk for authentication, active organization, live membership, invitations,
and its built-in `org:admin` / `org:member` roles. Make local PostgreSQL ownership
authoritative for owner-only operations. Keep the existing database-backed platform
administrator assignment. Do not build a second membership or invitation system.
This avoids requiring Clerk custom roles; other Clerk usage limits still apply.

An organization owner is an enabled local user whose `users.id` equals
`organizations.owner_user_id`, AND whose verified Clerk identity has current
membership in that organization. Keep owners as Clerk admins for consistent Clerk
management behavior. Never infer ownership from email, organization name, creator
role, token role, or public metadata. A missing membership denies customer access,
even when the local owner reference remains. Platform access uses its separate guard.

## Read-only evidence

Clerk CLI 3.4.0, invoked through `npx -y clerk@latest`, inspected the linked
Voice AI B2B application `app_3Jutc4GvIX2mItzJoPGOxccUsYi`.
Development: `ins_3JutbzyDziJRHNdc1E4BsganjHG`; no production instance linked.
Original organization: `org_3Jx1YFLsfVM3jJnKmcVTVHZFRdp`.
The memberships response contains one member:
`user_3Jx1ULmJ2F8pxqsAYyM8aWT48Or`, role `org:owner`.
Organization settings report `creator_role: org:owner`, membership limit 20,
and administrator deletion enabled. CLI doctor reports an expired/invalid login
token, but the explicitly targeted development Backend API reads succeeded.
No live DB reconciliation was performed; DB assignments must be verified before
cutover. These development IDs are not automatically valid in production.

Clerk documentation:
- https://clerk.com/docs/guides/organizations/control-access/roles-and-permissions
- https://clerk.com/pricing
- https://clerk.com/docs/guides/organizations/configure

## Existing implementation and exact change points

- `apps/api/voice_api/models/tenancy.py`: reuse `Organization.owner_user_id`,
  `PlatformAdministrator`, `OrganizationAudit`, and `OrganizationCreationClaim`.
  Owner FK is already non-null; uniqueness also limits each user to one owned org.
  Platform assignment is already a singleton. No new roles table is required.
- `apps/api/voice_api/core/security.py`: centralize effective access resolution;
  resolve verified live membership, local disabled status, local ownership, and
  capabilities. Do not return an unverified token role as the effective role.
  Replace the support path's synthetic `org:owner` principal with explicit support
  capabilities; support must not accidentally permit ownership transfer.
- `apps/api/voice_api/api/v1/endpoints/organizations.py`: derive `is_owner` from
  the local FK rather than `membership.role`; creation response currently hardcodes
  `org:owner`. Preserve transactional seeding/creation claims. Provisioning an
  existing unregistered org must not let any admin silently claim ownership:
  require a verified creator or an explicit audited platform adoption operation.
- `apps/api/voice_api/api/v1/endpoints/auth.py`: publish `is_owner`, effective role,
  and capabilities from the same resolver. Current context uses token roles and
  deliberately skips live membership checks; document any UI-only caching, while
  all mutations continue to check authoritative access.
- `apps/api/voice_api/api/v1/endpoints/openrouter.py` and
  `apps/api/voice_api/services/browser_session_service.py`: use shared access rules
  rather than scattered accepted-role lists. Browser session rechecks must still
  revoke access after membership removal or local disabling.
- `apps/dashboard/src/app/App.tsx`, `AppShell.tsx`, `app-context.ts`: remove owner
  decisions based on `useAuth().orgRole === 'org:owner'`. Use API ownership and
  capabilities. Clerk continues selecting organizations. Refresh context following
  transfer/member changes; hiding buttons never substitutes for API checks.
- Audit other branch/worktree versions before implementation: these findings are
  from the current main checkout, not an assertion that every branch matches it.

## Management rules

Members retain read/browser-test access; admins configure and manage ordinary
members. Owner additionally controls ownership transfer. Admins cannot remove or
demote the local owner through application endpoints. A second admin is not a
second owner. Default invitations remain member; granting admin requires an
authorized management operation. Owner membership removal through the external
Clerk dashboard must deny access and produce a reconciliation alert, not silently
elect another owner. Prefer application management UI for guarded changes.

Ownership transfer: owner selects an enabled existing member, backend validates
current membership and one-owned-org constraint, then ensures target is Clerk
admin before transactionally changing `owner_user_id`. Lock organization row and
require expected owner/revision; record actor and target in the same DB transaction.
Revalidate actor and target immediately before committing. Previous owner can stay
admin; changing their admin role is a separate explicit action. Clerk and PostgreSQL
cannot commit atomically: persist operation intent/status and reconcile failures.
A Clerk promotion followed by DB failure must not grant local ownership; a safe
retry must resume that operation instead of duplicating it.

Platform owner: retain the current `PlatformAdministrator` concept/name unless
renaming is separately desired. Management is an explicit audited transfer by the
current platform administrator to a verified enabled local user, with a singleton
row lock and revocation of existing support sessions. No customer admin can grant
platform access. Maintain an operator-run recovery command for loss of the sole
administrator, requiring explicit verified user ID and an audit record; never an
automatic first-login or email fallback. Support remains explicit and time-limited.

## Migration sequence

1. Inventory the exact deployment DB and Clerk instance pair. Export non-secret
   user/org/owner/platform assignments and Clerk memberships/invitations. Check
   pagination, missing/disabled users, owner membership, duplicate ownership, and
   conflicts between local owner FK and Clerk custom owner. Stop on ambiguity;
   resolve with an explicit reviewed mapping. Preserve all tenant/resource IDs,
   credential ciphertext, and encryption configuration.
2. Implement shared resolver and UI changes first. During transition tolerate
   legacy `org:owner` as admin-equivalent, but grant owner-only powers solely from
   the local owner FK. This allows old memberships to keep working during rollout.
3. Backfill only missing/incorrect local identity/ownership mappings using the
   reviewed inventory. Existing valid assignments need no data migration. If an
   operation ledger/revision is added, use a new Alembic revision; never rewrite
   applied migrations. Run a repeatable dry-run report and backup before writes.
4. Verify each local owner can exercise owner permissions with `org:admin` in
   tests/staging. Then change Clerk creator role to `org:admin`, convert existing
   custom-owner memberships to admin, and replace/reissue any pending invitations
   referencing custom roles. Paginate and reconcile every organization. This is
   future migration work, not authorized Clerk writes in this planning session.
5. Compare local ownership before/after and confirm owner/admin/member permissions.
   Retire custom roles only after all dependencies and memberships are cleared.
   Finally remove transitional legacy-role acceptance.
6. Production is a separate identity namespace. Provision/link production and map
   verified production users/orgs explicitly; do not copy development Clerk IDs
   into production assignments. If moving existing app data, map the external
   identity references while preserving local tenant IDs and resource ownership.

Rollback: keep DB ownership authoritative and restore the previous application
release only if it supports basic-role owners. Do not roll back to a release that
requires `org:owner` after converting memberships. Keep compatibility release and
inventory until production verification is complete.

## Validation and ordered implementation checklist

- [ ] Reconcile current DB assignments and all live Clerk memberships.
- [ ] Define shared effective access and capability contract; update ADR-0031.
- [ ] Fix backend ownership checks, provisioning, support separation, and context.
- [ ] Update dashboard/member management; regenerate OpenAPI client types.
- [ ] Implement audited owner/platform transfers and failure reconciliation.
- [ ] Test removed membership, disabled owner, stale token role, cross-org access,
  ordinary admin restrictions, support restrictions, concurrent transfers, unique
  owner conflicts, promotion/DB failure, and immediate platform revocation.
- [ ] Test creation with built-in admin and adoption without ownership escalation.
- [ ] Rehearse data mapping and role conversion on isolated DB/development instance.
- [ ] Review production mapping and execute staged cutover separately.

Open decisions: whether to retain one-owned-org-per-user and singleton platform
administrator restrictions; recommendation is retain both for this focused change.
No runtime, SIM7600, tool configuration, or provider-secret migration is required.

## 2026-10-04 application integration

The Pipecat worktree was fast-forwarded into local `main`. The application now
normalizes legacy `org:owner` membership to admin, reads live membership for the
context projection, derives owner status from the local owner FK plus live admin
membership, and keeps platform administration on its separate database assignment.
New local registration of a Clerk-created organization requires Clerk's recorded
creator; an arbitrary admin cannot claim it. The dashboard uses API capabilities
and owner status for its controls. These code changes do not change Clerk's
instance creator role or existing memberships.

Before switching Clerk to its basic roles, complete the inventory and staged
conversion above. The live development instance currently uses the custom
`org:owner` creator role. Application compatibility is intentional until every
membership and pending invitation has been reconciled. Ownership and platform
transfer workflows remain separate follow-up work; do not infer either transfer
from an admin role change.

The read-only cutover audit could not finish on 2026-10-04: the configured
local database at `localhost:55432/voice` refused connections, Docker's daemon
was stopped, and Clerk CLI doctor reported an expired authentication token.
The linked Clerk application has a development instance but no production
instance. No live creator role, membership, invitation or database assignment
was changed. Resume with an available database and refreshed Clerk CLI login,
then compare the exact owner IDs before converting the custom role.
