---
id: PLAN-0039
title: Isolated-database Clerk org demo and complete scoped dashboard
status: Superseded by PLAN-0040
date: 2026-09-28
related: [ADR-0030, ADR-0029, RFC-0014, PLAN-0038]
supersedes: [PLAN-0038 demo RBAC and invitation sections]
---

# Non-negotiable boundaries

> Historical plan only. PLAN-0040 is the sole implementation plan for the
> current org-only product. The second tenant layer and its routes, grants,
> invitations, and roles below must not be built.

- Keep Netlify React/Vite, one Render FastAPI + bundled Pipecat process,
  browser-test WebSocket, and Twilio. One active call overall. Keep SIM7600
  code for local use; report hardware unavailable on hosted Render.
- Use Clerk's standard organization invitation email and Admin/Member roles.
  No Google OAuth, custom Clerk roles, custom invitation email provider, FDE,
  workspace grant table, or workspace-only invitation email for this demo.
- Org members can access all workspaces in their org. A member of org A never
  gains access to org B or to an object owned by B's workspace, regardless of
  URL, body, nested ID, recording path, or provider callback.
- Keep the running main database and its volume untouched. This worktree uses
  Docker Compose project `voice-ai-clerk-worktree`, separate volume, port
  `55434`, and ignored `.env` pointing at the isolated `voice_full` database
  in that container. No migration is run against `55432`. Use a fresh schema
  here. If existing demo agents/data are
  needed, explicitly perform a read-only export from the main DB into this
  isolated DB or seed them anew; a fresh schema by itself contains none.

# Identity, organization and workspace model

`users(id, clerk_user_id UNIQUE, primary_verified_email, first_name,
last_name, created_at, updated_at, disabled_at)` is a profile/audit
projection. Do not store passwords or JWTs. Sync from Clerk with signed,
idempotent webhooks and reconcile at `/me`. Never authorize by email.

`organizations(id, clerk_org_id UNIQUE, name, owner_user_id, created_at)` and
`workspaces(id, organization_id, name, slug, created_at)` are application
catalogs. The local owner points to a user who is currently a Clerk org
admin. `organization_creation_claims(user_id PRIMARY KEY)` records the
one-org-creation rule even after transfer/deletion. New users without an
invitation can create one org and its first workspace through the app.
Disable generic Clerk org creation buttons that bypass this API. Users may
join other orgs via Clerk invitation without becoming owner.

`platform_admin_user_id` must be configured with a verified Clerk user ID,
not a default email. It is the sole cross-org override. A platform admin
may list/enter any org and workspace, but the API still resolves the target
and logs support access. Ordinary org admins/members see only orgs to which
Clerk currently grants membership. For the launch, org owner/admin can
author/publish, manage members, configure keys, and place calls; org member
can view org workspaces and test a browser call but cannot change org roles,
secrets, tools, or agent configuration. Final capability checks run in the
API, not just in the UI.

Every customer-owned table gets `workspace_id NOT NULL`, including agents,
versions, tool definitions/bindings, contacts and contact lists, KB/source/
chunk, integrations and encrypted secrets, settings, runs/calls/browser
sessions, evidence/analysis/artifacts/callbacks. Add same-workspace composite
FKs for nested references and workspace-scoped unique constraints. Runtime
endpoints are local hardware inventory, not customer-owned rows. Cross-tenant
lookups return 404, list queries filter workspace, and JSONB references are
validated on write and resolution. No global contact phone lookup or file
download. Maintain signed Twilio callbacks but derive tenant from stored
connection/run, not an untrusted callback parameter.

Fresh-DB onboarding creates `Original org` / `omkar` only after the verified
owner account exists; do not grant it to an email string. Seed approved
system tools and a starter agent transactionally per newly created workspace,
with a manifest version and idempotency key. Existing resources in a copied
snapshot retain IDs and are not overwritten. The operator-only legacy gate
stays fail-closed until every data route is workspace scoped, then is removed.

# Invitation and role APIs

Clerk sends org invitation email. No custom acceptance page is required:
configure Clerk to return to the app after its standard invitation flow.
The invited user signs up or signs in with the invited email, accepts the
invitation, selects the org, and immediately sees all its workspaces after
the server verifies current membership. Being signed in with a JWT alone
does not accept an invite. The invite UI never requests a workspace-specific
email. An existing org member simply selects another workspace.

All endpoints are `/api/v1`; Clerk session required except signed provider
callbacks. Resolve and authorize path IDs on every call:

| Endpoint | Required actor | Result |
| --- | --- | --- |
| `GET /me` | signed-in user | Profile, accessible orgs/workspaces, effective capabilities |
| `GET /orgs` | member or platform admin | Membership-filtered list, all only for platform admin |
| `POST /orgs` | user with no creation claim | Create one Clerk org + local org/first workspace + seeds idempotently |
| `GET /orgs/{org}` | member or platform admin | Org detail and workspace summary |
| `GET/POST /orgs/{org}/workspaces` | member/read; admin/create | Workspace list/create |
| `GET/PATCH /orgs/{org}/workspaces/{ws}` | member/read; admin/edit | Workspace detail/settings |
| `GET /orgs/{org}/members` | org member | Member list from Clerk |
| `POST/GET/DELETE /orgs/{org}/invitations[/{invite}]` | org admin | Clerk send/list/revoke; no app mail provider |
| `PATCH/DELETE /orgs/{org}/members/{user}` | org admin | Clerk Admin/Member role change or remove; guard owner/self |
| `POST /orgs/{org}/ownership-transfer` | current owner | Verified eligible member, local owner switch and Clerk admin role |
| `POST /auth/clerk/webhook` | signed Clerk webhook | Idempotent user/org sync and revocation |
| Existing resource/call/socket/file APIs | current member + capability | Scoped by resolved workspace and object parent |

Member removal and role downgrade must fail closed immediately, without
waiting on webhook delivery. Never grant role changes from a stale JWT claim
alone; query current Clerk membership or a securely invalidated local cache.
The platform admin cannot be demoted via an org-members page. Audit invitations,
role changes, removals, ownership transfer, and platform-admin entry.

# Complete dashboard route map

Use Clerk's built-in SignIn, SignUp, UserProfile, OrganizationSwitcher (with
generic creation suppressed), and organization invitation acceptance flow.
The application pages are:

| Route/page | Who sees it | Contents/actions |
| --- | --- | --- |
| `/` landing | public | Product summary, Log in, Sign up |
| `/sign-in`, `/sign-up` | public | Clerk email/password; first/last name required at signup |
| `/orgs` | signed in | Joined org cards; platform admin sees all orgs; create-one-org button only if eligible |
| `/onboarding/create-org` | no org/no claim | Org name and initial workspace name; no seeded email |
| `/orgs/:orgId` | member or platform admin | Org home, workspaces, recent runs, scoped navigation |
| `/orgs/:orgId/members` | member | All members and roles; admin can invite, change Admin/Member, remove; owner transfer only for owner |
| `/orgs/:orgId/invitations` | admin | Pending Clerk invitations, send and revoke |
| `/orgs/:orgId/settings` | admin | Org name, owner, ownership transfer; destructive actions guarded |
| `/orgs/:orgId/workspaces` | member | Every workspace in this org; admin can create |
| `/orgs/:orgId/workspaces/:wsId` | member | Workspace overview and browser-test entry |
| `/orgs/:orgId/workspaces/:wsId/settings` | admin | Workspace name, safe provider/Twilio key status and write-only update |
| `/orgs/:orgId/workspaces/:wsId/agents` and `/:agentId` | member | Scoped agents; edit/publish for admins |
| `/orgs/:orgId/workspaces/:wsId/tools` and `/:toolId` | member | Scoped seeded/customer tools; edit for admins |
| `/orgs/:orgId/workspaces/:wsId/contacts` and `/:contactId` | member | Scoped contacts and lists; edit for admins |
| `/orgs/:orgId/workspaces/:wsId/knowledge` | member | Scoped KB and sources; edit for admins |
| `/orgs/:orgId/workspaces/:wsId/integrations` | member | Safe status; admin configures/rotates |
| `/orgs/:orgId/workspaces/:wsId/runs` and `/:runId` | member | Scoped timeline, evidence, recordings |
| `/platform/orgs` | sole platform admin | All organizations with explicit enter action and audited context |
| `/platform/orgs/:orgId` | sole platform admin | Org and workspace inspection without a hidden client-only bypass |

The shell shows org/workspace selectors and effective role; it hides controls
the user lacks but does not serve as the security boundary. Navigation must
not render old global `/agents`, `/runs`, etc. once tenant routes are live.
Generate TypeScript contracts from OpenAPI. Add empty/loading/error/403 and
invite-pending states, plus refresh after invitation acceptance or role change.

# Ordered implementation and verification

1. Merge current `main` into this worktree (done; no rebase). Keep all existing
   dirty WebSocket work and SIM code intact.
2. Start isolated Compose project on `55434` (done), set ignored local `.env`
   to its URL (done), repair the pre-existing missing `0023` Alembic revision
   with a fresh-DB-only, fail-closed guard (done), fix the fresh-DB calendar
   index migration (done), and initialize the *empty* `voice_demo` database
   through `0026_tenant_catalog` (done). With explicit user approval, a full
   read-only source dump was then restored into a separate isolated
   `voice_full` database and upgraded to `0026`; `.env` now points there.
   Before any populated-database rollout, replace the guard with the full
   classifier data rewrite. Verify `current=head` and check `55432` was not
   written.
3. Add tenant/user/org schema and fresh-DB migration; implement create org,
   one-org claim, first workspace, tools/agent seed, Clerk invitation/member
   management, and `GET /me`.
4. Scope every existing API/service query and runtime/callback/file path;
   reject cross-workspace nested IDs, preserve WebSocket ticket semantics,
   and use an explicit SIM-unavailable response on hosted systems.
5. Build every dashboard page above, switch navigation to scoped routes,
   consume generated API types, and remove the old legacy-owner gate only
   after the backend enforces scope everywhere.
6. Test two unrelated orgs and one invited recruiter: no data leak through
   lists, object IDs, bindings, search, downloads, sockets, or callbacks;
   recruiter sees `Original org` / `omkar` only after accepting the email;
   member cannot mutate admin resources; removed member loses access;
   platform admin can enter all orgs with audit; one-org creation limit holds.
   Run Alembic, pytest, Ruff, OpenAPI generation, dashboard build, and a real
   audible browser call. Do not expose public signup before these gates pass.

# Known launch blockers at plan creation

- The pre-existing missing `0023_collapse_classifier_tools` revision now has
  a fresh-DB-only guard to permit isolated initialization. It intentionally
  fails on a populated legacy DB with the old tools/config. The historical
  classifier data rewrite remains required before a main/production DB upgrade.
- The user explicitly authorized a full clone including contacts, run
  history, encrypted integrations, and environment files. `voice_full` in
  the isolated container has the same initial counts as main (3 agents,
  10 tools, 3 contacts, 8 runs), then revision `0026` was applied there.
  The main DB was read only. The copied root `.env` is kept in the ignored
  `.env.main-copy` and layered *before* the worktree's ignored `.env` and
  Clerk `.env.local`; its main DB URL cannot override the 55434 URL.
  The earlier failed data-only copy may have partially populated the unused
  isolated `voice` DB; never select it for this worktree.
- A verified Clerk user ID, not the previously mentioned email alone, is
  needed to designate the sole platform admin/Original org owner. A read-only
  Clerk development user lookup for the stated founder address found no
  user yet; account creation is still required.
