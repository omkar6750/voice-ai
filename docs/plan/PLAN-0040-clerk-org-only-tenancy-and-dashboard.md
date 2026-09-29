---
id: PLAN-0040
title: Clerk Organization as the single customer tenant
status: Approved for implementation
date: 2026-09-28
related: [ADR-0028, ADR-0029, ADR-0030, RFC-0014]
supersedes: [PLAN-0037, PLAN-0038, PLAN-0039]
---

# Decision and current state

One Clerk Organization is one customer account and the only tenant boundary.
There is no application-owned tenant nested beneath it. Joining an org grants
access to that org's resources, subject to its Clerk role and the API's
capability checks. The recruiter gets access by accepting a standard Clerk
invitation to the founder's org. Do not create a separate invitation system,
membership grant, selector, settings page, route prefix, or role hierarchy
below the org. Use Clerk's free-tier basics: verified email/password, first
and last name, invitations, `org:admin`, and `org:member`; no Google OAuth,
custom Clerk roles, FDE role, or default recruiter email.

The linked Clerk development instance was checked on 2026-09-28. User
`user_3Jx1ULmJ2F8pxqsAYyM8aWT48Or` has verified primary email
`pawaromkar1654@gmail.com`; the only organization is `Original`, with Clerk ID
`org_3Jx1YFLsfVM3jJnKmcVTVHZFRdp`, created by that user. The user is its
current `org:admin`. Re-check these records immediately before database
backfill, then link cloned legacy data to the immutable Clerk org ID. Do not
infer identity from the name or create a duplicate. Store founder/owner and
sole platform-admin assignments in PostgreSQL using the verified Clerk user
ID and local user FK, with audit records. Never use an environment variable,
email string, frontend claim, or generic operator token to grant that role.

Current implementation is **not** tenant-safe yet. Migration 0027 retired the
empty extra tenant table added by 0026, added a unique org owner constraint,
and created the database platform-admin slot without rewriting the applied
0026 migration. The isolated worktree database is `voice_full` on Docker
project `voice-ai-clerk-worktree`, host port 55434, currently at revision 0037; it is a
full copy of the main database followed by the catalog migrations. The main
database remains on port 55432, revision
0025, and must not be migrated or written by this work. The copied provider
configuration is in ignored `.env.main-copy`, layered with the worktree's
Clerk `.env.local` and its isolated DB override. Do not print or commit keys.
Product routes now verify the active organization against the local registered
organization catalog, verify the user live through Clerk membership APIs, and
bind that organization ID to the request session. Original-only operations
retain a separate legacy-data check. Role gates and tenant query protections
remain in place. Product and organization-management gates also reject a local
`disabled_at` user while Clerk membership revocation propagates. Do not treat
this progress as proof of the entire API surface.

Implementation progress (2026-09-29): the isolated database is now at 0035,
with required organization columns on 37 customer-owned tables and existing
rows backfilled to Original. The organization access dependency binds the
verified local org ID to its request database session. Tenant-owned ORM reads/writes and Core/text
statements referencing tenant tables now fail closed without an org scope;
scoped ORM reads (including primary-key and aggregate reads) are filtered,
inserts are stamped, and cross-org writes fail.
Runtime scope bootstrap reads only a run's org identity through Core before
binding scope. Raw SQL reads still require explicit org predicates, raw SQL
cannot mutate org_id, and the table-by-table read/write audit remains open. Browser tickets carry that same org ID through
WebSocket status changes, evidence ingestion, diagnostics, and artifact
registration. Migration 0033 preflights tenant-to-tenant single-column foreign
keys and installs database guards that reject cross-org references. The
contact-variable metadata query now includes the active org predicate. This
is defense in depth, and the route gate now permits registered organizations
after live Clerk membership checks. This does not close the launch audit: the
API organization-creation saga and starter manifest,
Clerk sign-up, one-org eligibility flow, and create-org UI now exist. The
create-org action remains unavailable unless the account is eligible and
`VOICE_ORGANIZATION_CREATION_ENABLED` is enabled. Org exploration distinguishes
registered orgs and exposes the app/browser-test capability for each. Provider credentials
now have an org-owned encrypted table (0036), admin-only replace/remove
endpoints, and a write-only settings panel. Members see only configured/source
status. Browser, Twilio media, and local SIM calls load provider credentials
into an ephemeral settings copy selected from the persisted run's organization.
Existing process-environment provider keys are permitted only for
`LegacyDataTenant` (Original); non-legacy orgs get no global provider or
WhatsApp fallback. Original has not yet migrated its deployment keys into the
database and continues to use existing deployment values. The remaining
raw/bulk/non-FK audits are outstanding. Organization creation remains disabled
unless the deployment explicitly enables `VOICE_ORGANIZATION_CREATION_ENABLED`;
do not enable it for customer onboarding until the route/RBAC matrix and the
end-to-end second-org tests are complete.

Migration 0037 aligns previously drifting legacy schema details with the ORM:
classifier/interruption JSON columns become JSONB, historical browser session
timestamps remain nullable, and obsolete/missing indexes are reconciled. The
isolated database now passes `alembic check` against current metadata. This
does not certify tenant-query coverage or authorize multi-org access.

Migration 0030 changes `workspace_settings` from a database-global singleton
primary key to `(id, org_id)` and makes its tenant key required. The settings
API now reads and writes that singleton inside the authenticated org. Runtime
evidence, artifacts, claim/progress, Pipecat tool database access, and
browser/Twilio pipeline sessions derive scope from the persisted run. WhatsApp
webhook writes derive scope from the stored integration connection. Twilio
callbacks and media streams require a configured public URL and valid request
signature before processing.

# Identity, ownership, and roles

- Clerk is authoritative for user authentication, current org membership,
  invitations, and Admin/Member role. Our `users` row is a local profile and
  audit projection keyed by immutable `clerk_user_id`; email and names are
  display fields, never access grants. Sync via signed, idempotent Clerk
  webhooks and reconcile on authenticated `/me` so a delayed webhook does not
  block legitimate onboarding. Never store passwords or JWTs.
- `organizations` maps one local row to one `clerk_org_id`, with name, owner
  user FK, lifecycle timestamps, and seed version. The owner is an active
  Clerk `org:admin`, but owner status is a separate local invariant for
  transfer/removal protection. A unique owner FK means a user can own at most
  one org. A permanent `organization_creation_claims(user_id PRIMARY KEY)`
  means a user can create at most one org even after transfer/deletion. They
  may join any number of other orgs through invitations.
- The platform administrator is one database assignment in a singleton
  table/slot, initially linked to the verified founder ID above. Only a
  separately audited transfer can change it. A Clerk Dashboard team role
  does not grant platform access in the app. Platform-admin entry into a
  customer org must be explicit and audited, not a hidden UI bypass.
- `org:admin` may manage that org's members, invitations, provider keys,
  agents/tools/configuration, contacts, and calls, but may not transfer or
  remove the owner. `org:member` may view org data and run one browser test
  call; no member/role changes, publishing, secret writes, or Twilio dial.
  The owner has admin capabilities plus ownership transfer. The sole
  platform admin may list and enter all orgs; its actions are audited.
  UI visibility follows these capabilities, but FastAPI enforces them.
- New users without an invitation may create one org. App-controlled creation
  reserves a durable claim, creates the Clerk org, adds the local mapping,
  seeds starter content, and reconciles retries without creating duplicates.
  Hide generic Clerk create actions that could bypass the one-org limit and
  configure Clerk's create limit as defense in depth. Existing founder org
  adoption records a claim only after verifying its creator/owner relationship.
- Ownership transfer targets an active member who does not already own an org.
  Promote the target to Clerk admin, switch the local owner under a lock,
  record outcome/audit, and reconcile partial cross-system failures. Do not
  allow owner demotion/removal or an ownerless org.

| Actor | Org resources | Browser test | Twilio dial | Secrets | Members/ownership |
| --- | --- | --- | --- | --- | --- |
| Sole platform admin | All orgs, audited | Yes | Yes | Rotate, never read | Administer orgs; transfer platform assignment separately |
| Org owner | Own org, edit/publish | Yes | Yes | Rotate, never read | Invite/remove, make admins, transfer ownership |
| Org admin | Own org, edit/publish | Yes | Yes | Rotate, never read | Invite/remove non-owner, make admins |
| Org member | Own org, read | Yes | No | Masked status only | Read member list |
| Nonmember | None | No | No | None | None |

# Database and data migration

The empty speculative extra tenant table is retired. Next, migrate the
existing singleton settings record to one org-owned settings record.
Add `org_id NOT NULL` to every customer-owned table, including descendants,
not only roots. Inventory the final schema before migration, then scope at
least these existing groups:

| Model area | Org-owned records |
| --- | --- |
| Configuration | Settings, agents/versions, tools/versions, agent-tool bindings, contacts and named contact lists |
| Knowledge | Bases, sources, chunks, agent-knowledge bindings and embedding jobs |
| Integrations | Connections, encrypted secrets, media, inbound messages, calendar connections/secrets/OAuth states |
| Execution and evidence | Runs, calls, browser sessions, exchanges, messages, spans, tool invocations/results, classifier/context deliveries, interruptions, diagnostics, callbacks |
| Analysis and artifacts | Classifications, summaries, contact facts, recordings and all run artifacts |

Identity/catalog/audit rows are not children of an org. `runtime_endpoints`
is physical local SIM inventory, unavailable on hosted Render; do not expose
it as customer data. Add `(id, org_id)` unique parent keys and composite
foreign keys for cross-resource links (agent/version, agent/tool/knowledge,
run/contact/version/connection, call/run, integration/media/secret, and
evidence descendants). Validate embedded JSONB IDs at publish and snapshot
resolution. Scope names/phone uniqueness by org where appropriate. Every
lookup, list, search, background job, file path, artifact download, and
browser ticket must be org-bound. Return 404 for a foreign-org object.

Perform this on the isolated `voice_full` clone. The catalog-only 0027 migration
and identity assignment preserved the verified counts of 3 agents, 10 tools,
3 contacts, and 8 runs. Before the resource migration, record relationship
checks for published versions, bindings, evidence, and encrypted integrations.
Re-check the founder's current Clerk membership. The local user, org, creation
claim, and platform assignment rows are already inserted. Add nullable
`org_id`, backfill roots and derive descendants
from their parent chains, reject orphan or conflicting links, update all
readers/writers, then enforce NOT NULL and same-org constraints. Preserve IDs,
published config, evidence, ciphertext, and historical run hashes. Do not
silently re-seed or overwrite migrated tools/agents. Maintain a versioned
code-owned seed manifest for *new* orgs, copied idempotently per org.

Provider and Twilio credentials become org-owned encrypted records. Existing
copied environment keys are development bootstrap material for the founder's
org only; they must not become a global fallback available to new orgs.
The UI writes keys over HTTPS and shows only masked status. Runtime decrypts
only the selected org's keys immediately before a call. No plaintext appears
in API responses, logs, snapshots, diagnostics, or browser bundles.

# API and scope contract

The API verifies the Clerk session, resolves the requested `clerk_org_id`
to the local org, checks **current** membership/role (not only a potentially
stale token), checks capability, then filters both root and nested IDs by
`org_id`. The platform-admin override comes only from the DB assignment and
records its target org/action. A caller-supplied path, slug, body ID, or
active-org claim cannot grant access. Public provider callbacks verify
signature/state and resolve org from a stored connection/run. Same-process
Pipecat code calls local services with a trusted run/org context rather than
loopback HTTP. Keep the browser protobuf WebSocket and short-lived one-use
ticket; no Clerk token in its URL. Keep one global active-call slot for both
browser and Twilio. SIM-only actions return a clear unavailable error without
removing SIM code.

| `/api/v1` route family | Actor and behavior |
| --- | --- |
| `GET /me` | Clerk user, accessible orgs, current role/capabilities, ownership/creation eligibility |
| `GET/POST /orgs` | Membership-filtered list; platform admin sees all; POST creates one org with claim and seeds |
| `GET/PATCH /orgs/{org}` | Member read; admin/owner edit; platform entry audited |
| `GET /orgs/{org}/members` | Member list and Admin/Member roles from Clerk |
| `GET/POST /orgs/{org}/invitations` | Admin list/send standard Clerk org invitations |
| `DELETE /orgs/{org}/invitations/{id}` | Admin revoke pending Clerk invite |
| `PATCH/DELETE /orgs/{org}/members/{user}` | Admin role change/removal, owner and last-admin guards |
| `POST /orgs/{org}/ownership-transfer` | Owner-only verified transfer |
| `GET/PUT/DELETE /orgs/{org}/credentials[/{provider}]` | Member sees safe status; admin write-only rotate/delete |
| `GET/POST/PATCH/DELETE /orgs/{org}/contact-lists[/{id}]` | Org-scoped list and contacts; writes admin-only |
| `POST /auth/clerk/webhook` | Signature-verified, replay-safe identity/org reconciliation |
| `GET /platform/orgs`, `POST /platform/orgs/{org}/enter` | Sole platform admin, audited |
| Existing agent/tool/contact/knowledge/integration/run/call/browser/evidence/artifact routes | Require resolved org and capability on every verb and nested reference |

Remove or close the legacy unscoped route aliases only after the scoped client
is switched. Remove the old owner-email fallback and the speculative
`VOICE_PLATFORM_ADMIN_USER_ID` setting; neither is used to assign a role at
bootstrap or afterward. The user-supplied ID is recorded only following
Clerk verification. Invitations use Clerk's built-in
email and acceptance flow: a new user signs up, an existing user signs in,
and a signed-in user may complete acceptance; a JWT by itself is not an
accepted org membership. Removal/demotion takes effect promptly without
waiting for webhook delivery.

# Dashboard route and page map

Netlify serves React/Vite; FastAPI/Pipecat runs together on one Render service.
The dashboard uses the generated OpenAPI client and capability response; it
does not keep provider secrets or an operator token. Keep Clerk's SignIn,
SignUp, UserProfile, org switcher, and default invitation acceptance where
they fit; custom application pages enforce the one-org and owner rules.

| Route | Page and permitted actions |
| --- | --- |
| `/` | Public landing, Log in and Sign up |
| `/sign-in`, `/sign-up` | Clerk email/password, recovery, required first/last name |
| `/orgs` | Joined-org explorer; platform admin sees all; create-one-org CTA only if eligible |
| `/onboarding/create-org` | No-invitation new user creates their one org |
| `/orgs/:orgId` | Org home, agent test, recent runs, navigation, role badge |
| `/orgs/:orgId/members` | Members/roles; admin invite, promote/demote, remove; owner transfer entry for owner |
| `/orgs/:orgId/invitations` | Admin send/list/revoke Clerk invitations; pending/accepted feedback |
| `/orgs/:orgId/settings` | Org profile, owner, write-only provider and Twilio keys/number status; admin edit |
| `/orgs/:orgId/agents`, `/:agentId`, version editor | Org agents; admin edit/publish, member inspect/test |
| `/orgs/:orgId/tools`, `/:toolId` | Org-owned seeded/customer tools; admin edit |
| `/orgs/:orgId/contacts`, `/:contactId`, `/contact-lists` | Org contacts/lists and timeline; admin write |
| `/orgs/:orgId/knowledge`, `/:baseId` | Org KB/sources; admin write |
| `/orgs/:orgId/integrations`, `/:connectionId` | Safe status; admin connect/rotate/disconnect |
| `/orgs/:orgId/runs`, `/:runId` | Org timeline, evidence, recordings/downloads |
| `/platform/orgs`, `/platform/orgs/:orgId` | Sole platform admin explores all orgs and explicitly enters an audited context |

The shell has an org switcher, user menu, and current capability badge; no
second selector. Every page handles loading, empty, error, removed-membership,
and stale-role states. URL navigation does not authorize data. The older
global `/agents`, `/runs`, etc. paths redirect only after the backend is
tenant-safe. Do not display disabled SIM/hosted callback actions as working.

# Hosting, delivery order, and acceptance

Keep the earlier topology decision: Netlify hosts only the built dashboard;
one Render web service hosts FastAPI plus `voice_runtime`, one worker and one
active call. Browser audio uses the Pipecat WebSocket transport; Twilio uses
signed HTTP callbacks and media WebSocket. Require exact CORS/WS origins,
Clerk authorized parties, production keys, TLS/WSS, persistent PostgreSQL,
backups, and object storage/retention for durable recordings. Do not expose
local SIM COM operations on Render. Leave callback/calendar actions out of
the demo unless separately validated. Do not edit `scripts/demo_call.py`.

1. **Documentation first (done):** mark 0030–0032 historical; settle the
   org-only model and update the owning ADR/RFC before code or DB writes.
2. **Identity proof and catalog correction (done on isolated DB):** verified
   supplied user/org in Clerk, retired the empty nested catalog through 0027,
   and persisted sole platform-admin assignment and owner in DB, never env.
3. **Org backfill (staged):** migration 0029 added nullable `org_id` to all
   37 customer tables in the isolated clone and linked all existing records
   to the verified Original org. IDs, row counts, and ciphertext are preserved.
   Migration 0030 made workspace settings independently addressable per org.
   Migration 0031 now enforces non-null `org_id` for every customer row after
   an all-table preflight (0034 schema-discovered and corrected a missed
   classifier-results column). Migration 0032 changes uniqueness for
   agent/tool/KB names, integration labels, and contact phone numbers to be
   per-org after a duplicate preflight. Migration 0033 adds same-org guards to
   tenant-to-tenant single-column references.
4. **API and runtime scope:** replace the old single-user gate only after all
   interactive routes, callbacks, WebSockets, downloads, and same-process
   service calls enforce org scope. Add negative cross-org tests per route.
5. **Org management and dashboard:** implement the route map above, Clerk
   invitations/role changes, one-org creation, owner transfer, seed and
   write-only org credentials; regenerate OpenAPI types and test UI flows.
6. **Launch gates:** two unrelated orgs with duplicate agent/tool/contact
   names cannot read or bind each other's records; the recruiter sees the
   founder's org only after Clerk invitation acceptance; a removed member
   loses access; member/admin/owner/platform actions match the matrix;
   original IDs, published versions and evidence remain intact; browser and
   Twilio cannot overlap. Run isolated Alembic upgrade/check, full pytest,
   Ruff, OpenAPI generation, dashboard build, audible browser call and
   signed Twilio test. Public customer onboarding stays closed until all
   tenant gates pass.

# Explicit non-goals and current blockers

## Implementation checkpoint (2026-09-29)

The current Clerk slice provides membership-filtered organization discovery,
standard Clerk email invitations, pending-invitation management, Admin/Member
role changes, owner transfer with a successful-transfer audit, and owner/last-admin removal guards. A joined Clerk organization
without a local mapping is visible as **setup pending** but cannot open legacy
resources. Protected product API requests now require a registered active org
and verify live membership through the Clerk Backend API SDK. Members receive
reviewed reads plus browser-test create/ticket/end; every route without the
explicit `@allow_organization_member` marker defaults to org-admin-only. Each
request binds the local org ID before tenant ORM work. The Original org alone
continues to receive legacy environment-provider-key fallback and Twilio dial
capability. The generalized gate is backed by tenant filters and database
reference guards, but the table-by-table authorization/query audit remains
open. Tests cover registered non-Original scope binding, fail-closed unmarked
routes, annotated reads, legacy-only access, and browser-session lifecycle.
Registered organizations use their own resource scope and the org-scoped
membership/invitation/ownership and encrypted provider-key pages.

Authenticated `GET /me` now fetches the caller's verified primary email and
profile fields from Clerk and idempotently upserts the local `users` projection.
It does not treat profile or email data as an access grant. Membership and roles
continue to be read live from Clerk; a signed webhook/replay ledger remains
deferred because the current application does not rely on webhook-delayed
membership state. A database-assigned platform administrator can call
`GET /platform/orgs` to discover registered organization names and owner IDs.
The platform-admin dashboard can explicitly enter one registered org through a
30-minute support session. The API returns a random bearer secret once, stores
only its SHA-256 digest, binds it to the authenticated database-assigned
platform administrator and target org, revokes that admin's prior active
support session, and validates it on every scoped request. Start and end are
recorded in `organization_audit`; exit revokes the session. The dashboard keeps
the secret in component memory, sends it only in `X-Platform-Support-Session`,
shows the target in a support-mode banner, disables Twilio dialing, and offers an
explicit exit. Clerk session authentication remains mandatory; Clerk role or
org claims cannot create this access. OpenAPI and dashboard types include the
support routes. The generated TypeScript OpenAPI
contract is checked in so a clean Netlify checkout can type-check without the
ignored local `data/openapi.json`; regenerate it with the documented OpenAPI
export + dashboard `npm run generate` workflow whenever API contracts change.
The generated runtime schema remains ignored because dashboard source does not
import it.

Still required before production onboarding: finish the row-level API/RBAC
matrix review across every customer route; audit all raw SQL, bulk operations,
non-FK resource references, background jobs, and webhook paths; finish UI
coverage for all resource areas; verify support-session expiry, revocation, and
platform-admin isolation against PostgreSQL; and run an authenticated two-org
end-to-end flow including invitation, org switching, create/read/update access,
browser test call, and negative cross-org probes. Organization creation remains
feature-flagged until these gates pass. Do not run the resource migration
against the main database.

`GET /api/v1/me` now returns joined orgs, current capabilities, platform-admin
status, and creation eligibility. The org-creation endpoint is implemented but
remains closed unless the deployment enables its explicit feature flag.
Migration 0028 fixed the legacy mapping independently of owner transfer and
added an ownership audit table. Migration 0029 temporarily suspends only named
application immutability triggers during backfill and restores them in the
same transaction. Migration 0030 changed workspace settings to a compound
`(id, org_id)` key; 0031 initially enforces required tenant ownership on most
customer rows; 0032 makes principal customer-facing name/phone uniqueness
per-org; 0033 guards single-column references between tenant-owned rows; 0034
   schema-discovers and makes every `org_id` column non-null. Migration 0035
   adds per-org starter-manifest version tracking; the creation API provisions
   the Clerk org, local owner/claim, starter tools/agent, and settings in one
   compensating transaction.
Runtime evidence, artifacts, call progress, Pipecat database
tools, and telephony processing now derive org context from the run or stored
integration. Public WhatsApp webhook handlers use a strict scalar bootstrap by
the connection's opaque primary key before loading the integration, then bind
scope before reading secrets or writing receipts; the PostgreSQL receipt test
exercises fresh, initially unscoped request sessions. Knowledge background
ingestion now bootstraps only `org_id` by source primary key and binds that same
tenant before its reads in both fresh build sessions. The Google OAuth callback
similarly binds from its high-entropy unique state hash before loading its
tenant-owned state and integration. Raw knowledge retrieval filters
base/source/chunk org IDs. Twilio requests fail closed if the public URL/signature is not
configured. This is partial tenant hardening; do not infer full isolation or a
clean Alembic schema check from the migration.

- No nested customer tenant, second-level membership, or additional role set.
- No platform FDE, OAuth social login, billing, concurrency, or separate
  runtime server for this launch.
- The historical `0023` classifier migration is only a fresh-DB guard; a
  populated database with old classifier tools needs the full rewrite before
  that migration can be used for a production upgrade.
- The full clone is isolated; its org catalog is not a complete authorization
  model. The founder's identity, org, creator relationship, and admin
  membership were verified in Clerk on 2026-09-28 and linked in the isolated
  DB. Re-check current Clerk membership before the resource backfill.

## Verification update (2026-09-29)

Integration follow-up: see PLAN-0041 for the main-runtime merge, unified migration
head, additional live-host tenant bindings, and remaining production gates. The
application now defaults organization creation to enabled for the requested
development workflow; earlier statements below describe historical rollout
restrictions, not the current default. Live Clerk settings and production
acceptance are still separate checks.

The active Clerk worktree database is at migration 0038; the main database was
not used for these checks. The complete unit suite, PostgreSQL integration
suite, Ruff, Alembic metadata check, and dashboard production build pass. The
integration suite exercises tenant isolation against the isolated database.
The build still reports the existing large JavaScript chunk warning. A stale
knowledge build against a deleted source now returns a no-op rather than a
404 after scope bootstrap. The dashboard has a role-derived organization
access context and visible read-only member treatment across resource details:
admin mutations are hidden or disabled for agents, tools, contacts, knowledge,
integrations/media/secrets, settings, and callback dispatch; members retain
read navigation and browser test access. The API client blocks member
mutations except browser-session lifecycle requests, while server-side Clerk
role checks remain authoritative. The public landing copy now accurately
describes sign-up and organization onboarding.

Not yet proven: live Clerk invitation acceptance with a second user, end-to-end
two-org switching and cross-org negative probes in a signed-in browser, and an
actual hosted voice call. Keep organization creation feature-flagged until the
complete API/RBAC matrix and those external end-to-end checks pass. The table-
by-table audit of bulk deletes, non-FK references, background tasks, and every
customer-facing route also remains open; passing suites alone are not a
substitute for that audit.
