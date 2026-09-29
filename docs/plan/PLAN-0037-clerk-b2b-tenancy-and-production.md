---
id: PLAN-0037
title: Clerk B2B onboarding, workspace tenancy, RBAC, BYO credentials, and production calls
status: Superseded by PLAN-0040
date: 2026-09-27
related: [ADR-0028, RFC-0014, RFC-0003, RFC-0004, ADR-0006, ADR-0007]
---

# Scope and recommendation

> Historical plan only. PLAN-0040 is the sole implementation plan for the
> current org-only product. The second tenant layer and its routes, grants,
> invitations, and roles below must not be built.

Launch as B2B: organization -> workspaces -> agents and runs. A solo user is an
organization of one, which avoids maintaining a second personal-account model.
The first release should use one default workspace per new org, optional extra
workspaces, three customer roles, and two platform roles. Avoid custom Clerk org
roles, SSO, billing automation, nested teams, and workspace-level owner roles at
launch. Add quota tiers after the access boundary and call economics are measured.

Implementation began in the `codex/clerk-integration` worktree. The new Clerk
development application is linked, Organizations are enabled, and the React/Python
identity foundation is wired: sign-in/sign-up, a verified `/api/v1/auth/me`
endpoint, and a server-side legacy-owner gate. The dashboard no longer asks for
or stores the operator token; it sends Clerk session tokens. In-process browser,
Twilio, and SIM7600 runtime operations call local persistence directly. Only
external worker-facing routes use a separate service token. The temporary
owner mapping uses
`VOICE_CLERK_LEGACY_OWNER_EMAIL`, with a verified primary email lookup, until the
account is created and `VOICE_CLERK_LEGACY_OWNER_USER_ID` can be pinned. Missing
`VOICE_RUNTIME_SERVICE_TOKEN` disables external worker writes but not local calls.
Human callback slots require `VOICE_CALLBACK_SLOT_SIGNING_KEY` when scheduling
is enabled. No tenant migration, seed, or live call has been performed yet.
This branch merged committed `main` through `0a7a446`; any
later changes must be merged, never rebased. Preserve the protected demo.
The ignored root `.env.local` holds development Clerk credentials. Vite reads only
its publishable key; it must never load the backend secret into the client bundle.

## Product model and ownership

```text
Platform administrator (exactly one) / FDE staff (zero or more)
  └─ all customer organizations, under audited support access

Clerk user ──< Clerk organization membership >── Clerk Organization
                                                   │ 1:1
                                                   ▼
                                            local organizations row
                                                   │ 1:many
                                                   ▼
                                                workspaces
                                                   ├─ agents/versions/bindings
                                                   ├─ tools/versions (copied from catalog)
                                                   ├─ KBs, contacts, integrations, credentials
                                                   └─ runs/calls/browser sessions/evidence
```

- `organizations`: local UUID, unique `clerk_org_id`, slug/name cache,
  `owner_clerk_user_id`, `created_by_clerk_user_id`, status, timestamps. Ownership
  is unique because it is one column on one org. A separate immutable
  `organization_creation_claims(clerk_user_id PRIMARY KEY, organization_id)`
  makes "a user can create only one org" durable, even if ownership changes or
  an org is later archived. Platform-created orgs have a recorded target creator.
- `workspaces`: UUID, org FK, unique `(org_id, slug)`, name, status, created_at.
  At least one active workspace per active org. `workspace_settings` becomes
  `(workspace_id PRIMARY KEY, revision, config)`; migrate singleton `id=1` into
  the initial workspace.
- `workspace_memberships`: `(workspace_id, clerk_user_id)` unique, role enum
  admin/editor/viewer, timestamps, grantor. Org owner/admin inherit access to
  all workspaces without rows. Ordinary members need explicit workspace rows.
- `workspace_invitations`: Clerk invitation ID, org/workspace, normalized email,
  intended workspace role, inviter, state. A verified accepted invitation leads
  to one idempotent membership grant. Existing org members can be added directly.
- `platform_staff` and `platform_staff_invitations`: Clerk user ID or Clerk
  invitation ID, role `platform_admin`/`fde`, state, actor, timestamps. A database
  unique partial index permits one active platform admin. Bootstrap uses an
  explicitly chosen Clerk user ID after that user's identity is verified.
- `provider_credentials`: workspace FK, provider, key purpose, encrypted payload,
  key ID, status, version, masked suffix, created/rotated timestamps. Unique active
  key per workspace/provider/purpose. The keyring is deployment-managed; no
  encryption key is stored with ciphertext.
- `seed_catalog` (versioned manifest in repository) describes approved registered
  tool definitions, starter agents, and their bindings. Import into each new
  workspace transactionally, tagging imported rows with manifest version. Updates
  offer explicit new starter versions; they never overwrite a customer's edits.

Keep Clerk org and member identity authoritative. Store a small local cache for
joins and audit; reconcile signed-in users synchronously during onboarding and
use verified Clerk webhooks for eventual updates and removals. For organization
creation, first reserve the creation claim under a DB unique constraint, call
Clerk's Backend API with an idempotency/recovery key, then finalize local org and
workspace rows. If Clerk succeeds but DB commit fails, retry/reconcile by the
reserved claim and Clerk org ID; do not create a second org. Configure Clerk's
per-user organization creation limit to one as defense in depth and hide/bypass
its generic create affordances. A creation limit alone cannot express all local
invariants or preserve history after deletion.

## Access rules

Authentication and authorization are distinct: verify the Clerk session JWT,
accepted origin/authorized party, active org, and current membership; then load
the path's org/workspace and compare IDs. Root resource lookups are filtered by
workspace ID, including lists, detail, version, search, download, and WebSocket
handshakes. Return 404 for inaccessible IDs. `GET /me` returns effective roles
and allowed workspaces for navigation, never a secret.

| Actor | View/edit workspace data | Calls/tests | Secrets | Members/workspaces | Ownership/platform |
| --- | --- | --- | --- | --- | --- |
| Platform admin | all, all actions | all | set/rotate, never reveal | all | grant/revoke FDE; bootstrap successor by controlled transfer |
| FDE | all, all actions with support audit | allowed with quotas and audit | set/rotate, never reveal | support manage, cannot remove owner | cannot transfer owner or grant staff |
| Org owner | all org workspaces | yes | set/rotate | invite/remove, make admin, create workspace | transfer org ownership |
| Org admin | all org workspaces | yes | set/rotate | invite/remove ordinary users; make admins; create workspace | cannot remove/demote owner |
| Workspace admin | assigned workspace, edit/publish | yes | set/rotate for assigned workspace | invite/remove members of assigned workspace | no org or platform changes |
| Workspace editor | assigned workspace, edit/publish | yes | no | no | no |
| Workspace viewer | assigned workspace, read | no | no | no | no |

Only org owner/admin or platform staff may grant `org:admin`; only the owner may
transfer ownership. A workspace admin can invite to their workspace with Clerk
org role `org:member`, then assign the local workspace role upon acceptance.
Org admins cannot demote/remove the owner, even though Clerk's default admin role
has broad membership rights. All sensitive flows go through app endpoints and a
reconciliation check repairs or blocks out-of-band Clerk dashboard changes.
Transfer is a locked, audited transaction: target must be an active org member;
promote target to Clerk `org:admin`, change local owner after confirmation, keep
old owner as `org:admin` unless explicitly demoted, refresh sessions, disallow
last-owner removal, and retry safely if the Clerk and DB steps diverge. FDE access
is distinct from Clerk org membership; staff never need to be inserted as members
of each customer org.

For production cutover, do not expose any old `VOICE_OPERATOR_TOKEN` route to
internet users. Worker requests use short-lived service credentials bound to a
run, workspace, allowed operation, and nonce. Twilio/Meta webhooks verify provider
signatures and derive tenant from the stored connection/correlation ID. OAuth
callbacks verify stored state and bind it to the initiating workspace/user.

## API inventory and file changes

The REST prefix remains `/api/v1`; public health and signed provider callbacks
are explicitly separate. Keep existing resource URLs initially, but require an
active workspace resolved from a dedicated header or route selector *and* server
membership. Prefer canonical `/api/v1/orgs/{org_id}/workspaces/{ws_id}/...` for new
endpoints and gradually move old resource routes behind the same dependency.
Never trust caller-supplied `workspace_id` as proof of access. Drop or internally
alias `/api` compatibility routes before production so the policy has one surface.

| API | Methods | Authorization / behavior |
| --- | --- | --- |
| `/me`, `/me/workspaces` | GET | authenticated profile, allowed orgs/workspaces, effective capabilities |
| `/orgs` | GET, POST | own memberships or staff; POST one-org creation claim and default workspace |
| `/orgs/{org}` | GET, PATCH | member read; owner/admin edit profile; FDE audited support |
| `/orgs/{org}/members` | GET | org members or staff; include workspace assignments |
| `/orgs/{org}/invitations` | GET, POST | owner/admin; create Clerk invite, optional workspace intent |
| `/orgs/{org}/invitations/{id}` | DELETE | authorized revoke; local intent retired |
| `/orgs/{org}/members/{user}` | PATCH, DELETE | role change/removal; owner guard |
| `/orgs/{org}/ownership-transfer` | POST | owner only, locked transfer protocol |
| `/orgs/{org}/workspaces` | GET, POST | accessible list; owner/admin create; initial seed transaction |
| `/orgs/{org}/workspaces/{ws}` | GET, PATCH, DELETE | scoped view/edit; archive with dependencies checked |
| `/orgs/{org}/workspaces/{ws}/members` | GET, POST | workspace/admin or org/admin; invite/add |
| `/orgs/{org}/workspaces/{ws}/members/{user}` | PATCH, DELETE | workspace/admin or org/admin, prevent self lockout |
| `/orgs/{org}/workspaces/{ws}/provider-credentials` | GET, PUT, DELETE | metadata and write-only rotate/delete; workspace admin+ |
| `/orgs/{org}/workspaces/{ws}/provider-credentials/{provider}/test` | POST | bounded provider validation, safe status only |
| `/platform/orgs`, `/platform/staff`, `/platform/staff/invitations` | GET/POST/DELETE as appropriate | platform admin only for staff; FDE org explorer with audit |
| `/auth/clerk/webhook` | POST | public only to Clerk, raw body signature verification, replay/idempotency |
| `/browser-sessions`, `/calls`, existing resource endpoints | existing verbs | tenant and capability checks; create uses selected workspace |
| `/runtime/...`, `/runs/{id}/evidence` | existing verbs | worker credential scoped to run/workspace; never user token forwarding |
| Twilio/WhatsApp webhook + calendar OAuth paths | existing verbs | provider signature or OAuth state; resolve workspace from stored object |

Concrete code ownership:

- `apps/api/voice_api/core/config.py`: Clerk keys/JWKS, allowed origins, service
  token issuer, public URL, keyring, quotas. Fail startup in production when absent.
- `apps/api/voice_api/core/security.py` and `api/deps.py`: replace `require_operator`
  with Clerk Python SDK `authenticate_request` and typed `Principal`,
  `require_org`, `require_workspace`, `require_capability`, `require_staff`, and
  worker auth dependencies. Check `authorized_parties`; do not decode unsigned
  JWTs or infer staff from client metadata.
- `apps/api/voice_api/models/{configuration,integrations,knowledge,evidence,analysis,operations,artifacts}.py`:
  add scope to roots and guarded cross-resource links. Add `models/tenancy.py` and
  `models/provider_credentials.py`; generate migrations only after merging the
  current checkout's pending migration 0023/0024.
- `apps/api/voice_api/api/v1/endpoints/*`: inventory every operation, including
  provider catalog, config schema, tools validation, media, artifacts, calendar,
  callback scheduling, browser offers, run evidence and endpoint probe. Apply
  role-specific scopes at both query and object lookup. Never return platform
  provider catalog status based on unrelated tenants' keys.
- `services/{resolution_service,provider_registry,browser_session_service,call_service,twilio_service,knowledge_service}.py`
  and `packages/voice_runtime/voice_runtime/execution/{native,runner,evidence_client}.py`:
  resolve tenant-bound versions/keys, keep secrets in process memory, pass a
  credential object to Pipecat providers, and scrub metrics/diagnostics. The
  runtime snapshot includes workspace and credential *reference*, never plaintext.
- `apps/dashboard/src/main.tsx`, `app/{App,api,AppShell,AppRoutes}.tsx`: add
  `ClerkProvider`, getToken-based request client, auth route guard, org/workspace
  selectors, and capability-aware navigation. Generate TS API contracts from
  OpenAPI rather than duplicating DTOs.

Existing endpoint policy inventory (apply to every verb in each file, including
non-obvious subroutes):

| Existing endpoint file / routes | Minimum policy and scope |
| --- | --- |
| `agents.py`, `tools.py` | workspace viewer read; editor create/edit/publish/activate; workspace admin archive/cleanup; all bindings must stay in one workspace |
| `contacts.py`, `knowledge.py` | viewer read/search; editor write/upload/rebuild; workspace ID on contacts, sources, chunks and embedding jobs |
| `integrations.py`, `calendar.py` | viewer sees safe metadata; workspace admin manages connections/secrets/OAuth; runtime calendar actions use run-bound identity; public callbacks use signatures/state |
| `runs.py`, `calls.py`, `browser_sessions.py`, `dial_catalog.py` | viewer reads authorized evidence; editor or higher starts/tests/calls; selected agent, contact, number and connection must share workspace; browser offer/patch/delete check session owner or workspace role |
| `analysis.py`, `evidence.py`, `artifacts.py` | viewer reads; writes/registration only worker identity; downloads are scoped; expiration only scheduled service identity |
| `callbacks.py`, `reconciliation.py` | editor schedules; workspace admin manually launches/reconciles uncertain calls; automated launch uses service identity and workspace quota |
| `execution.py`, `telephony.py` | physical endpoint administration is platform staff or explicitly assigned workspace admin; claims/progress/status are worker only; Twilio callbacks/media are signature validated and linked to stored run/workspace |
| `providers.py`, `workspace.py` | provider catalog derived from selected workspace's saved keys; config schema authenticated; workspace settings viewer read/admin write; no singleton fallback |

For each API, write a route-level test asserting both required capability and
two-tenant isolation. WebSocket, upload, OAuth, and provider callback tests must
cover the non-JSON authorization paths. Remove or separately protect any route
that cannot be assigned a tenant before enabling public accounts.

## UI journeys

1. Public `/`: landing page explaining browser testing and bring-your-own
   credentials, with Sign up and Log in. No operator token form in production.
2. `/sign-up`, `/sign-in`: Clerk themed embedded UI. Email/password or selected
   social methods are configured in Clerk. Clerk handles forgot/reset password;
   app hosts return routes and never stores password-reset tokens.
3. Invitation link: Clerk accepts identity/org membership, then the app's
   `/onboarding/invite` reconciles the invitation, assigns the workspace, and
   opens it. Do not create another org for invited users. Pending/ineligible
   grants display a recoverable state.
4. New user without invitation: `/onboarding/create-org` collects organization
   name and first workspace name (default suggested); creates both once, seeds
   starter content, then opens `/o/:orgSlug/w/:wsSlug/agents`. User can create
   only one org, but can accept invitations to other orgs.
5. App header: org selector and workspace selector, user menu, role badge.
   `/organizations` shows only memberships; FDE has a separate audited
   `/platform/organizations` explorer with search and explicit support context.
6. Organization Settings: Members, Invitations, Workspaces, Ownership. Owner
   transfer has target confirmation; admins cannot see its action. Workspace
   Settings: Members, Provider keys (masked status, test, rotate, delete), Twilio
   connection/numbers, usage/limits. Viewers get read-only pages.
7. Agents/Tools: current preserved agents/tools in `Original org / omkar`;
   new workspaces show starter copies tagged "Example", with duplicate/edit
   affordance. New users can browser test once their selected provider keys are
   configured. An empty/error state names the missing provider key, without
   exposing another workspace's status.
8. Platform Settings: only platform admin may invite/revoke FDE. FDE support
   view shows current customer context and records all writes/calls.

## Data migration and seed safety

1. Inventory every live table, foreign key, JSONB embedded ID, file path, and
   background job payload. Snapshot and back up the DB. Audit row counts and
   orphan references; pin the current published agent/tool versions.
2. Add local org/workspace tables and nullable workspace FKs to root rows.
   Create Clerk `Original org`, identify the owner's verified Clerk user ID, and
   create local workspace `omkar`. Store the exact Clerk org ID. No automatic
   owner selection from an email or existing provider credential.
3. Backfill current agents, tools, contacts, KBs, integrations, calendar records,
   endpoints (mark physical SIM7600 as platform-owned or dedicated workspace),
   runs/calls/browser sessions/callbacks/artifacts/evidence and singleton settings.
   Keep all existing IDs. Derive children from root FKs and assert each chain is
   within one workspace. File/media paths gain namespaced access controls; move
   files only with a manifest and verified checksums, never inferred paths.
4. Scope uniqueness: global `agents.name`, `tools.name`, contact phone, integration
   label, etc. become `(workspace_id, value)` where appropriate. Keep immutable
   historical IDs and publication guards. Add composite same-workspace FKs or
   explicit DB validation for agent-tool/KB, run-contact/version/connection,
   callback-calendar, evidence links, and media. Cross-workspace references fail.
5. Ship dual-read migration code, verify counts/references/snapshot hashes and
   the root workspace in a staging restore, then make ownership non-null and cut
   over every API/worker. Disable the shared operator token on public routes.
   Only after a clean cutover remove old singleton/compatibility pathways.
6. Seed catalog is separate from migrated rows. Add fixture tests for repeated
   onboarding, retry after partial Clerk success, starter version updates, and
   preserving published edits. No seed rerun may overwrite existing versions.

## BYO provider keys, tiers, and calls

Each workspace may set its own Groq/Gemini/Sarvam/Cartesia/JEV keys and Twilio
account credential. The UI sends values only on write over HTTPS; API encrypts
with the existing Fernet-style keyring, returns presence/last-four/last-tested,
and never allows GET plaintext. Rotation creates a new version and invalidates
cached provider catalogs; running calls keep their already chosen provider key in
memory until completion. New calls fail closed if the required key is absent or
revoked. Audit every write and test. Restrict staff access to masked status.

Keep product access tiers separate from RBAC. Launch with `trial` and `standard`
capability/quota records on the workspace or organization: browser-test minutes,
concurrent calls, phone calls, storage/retention, and monthly limits. Define exact
values after provider cost testing. Trial can allow browser test with user keys
and zero phone calls; standard can allow phone calls after Twilio connection and
verified numbers. A quota denial is an explicit 429/403 with a safe reason; role
checks still apply. Do not gate the ability to read one's own data on a provider
key. Clerk Billing may later own payment collection, but access tiers live in
application policy until a billing decision is made.

The existing Twilio Voice integration already supports account credential
storage, verification, number sync, and server-initiated outbound calls. Scope
it to workspace, verify ownership of the selected from-number, validate Twilio
webhooks, and bind each call's connection ID and workspace in the immutable
run record. Browser test uses the WebSocket/browser session API and the
workspace's AI provider keys; it does not require Twilio. A browser softphone
that calls phone numbers through the user's Twilio account is a *separate*
feature requiring Twilio Voice JS SDK, per-workspace TwiML app and short-lived
Twilio Access Tokens. Do not conflate that with current browser agent testing.

## Production hosting and threat model

- Host the React build behind HTTPS and FastAPI behind the same trusted origin or
  explicitly configured CORS origins. Clerk production keys/domain, organization
  mode `Membership required`, sign-in redirect URLs, and webhook signing secret
  must be configured. Review Clerk membership and MRO limits before launch.
- Run PostgreSQL/pgvector with backups and restore drills. Keep Fernet keyring,
  Clerk secret, JWT verification key, service signing key, provider fallback keys
  (if any), and Twilio secrets in a deployment secret manager. Version/rotate
  encryption keys and retain old keys until all ciphertext is re-encrypted.
- Move recordings, debug files, and integration media from local paths to
  workspace-prefixed object storage before multi-instance hosting. Download
  endpoints reauthorize each object; URLs are short-lived and tenant-bound.
- Public Twilio bidirectional media needs reachable TLS/WSS and stable routing
  to the run's worker. Use a worker queue/lease and shared session store for
  browser calls; the present in-process session map cannot span replicas.
- Rate-limit signup, invites, key tests, browser offers, calls, and artifact
  downloads. Enforce per-workspace concurrency and spend caps. Prevent a worker
  from claiming another workspace's run. Instrument access denials and staff
  support actions. Do not log JWTs, decrypted provider keys, or customer audio.
- Serve only necessary public endpoints: health, Clerk webhook, signed provider
  callbacks, and OAuth redirect. Dev routes, OpenAPI/docs, `/api` compatibility,
  and operator-token bypass need an explicit production access policy.

## Delivery slices and gates

1. **Identity foundation:** install current Clerk React SDK and Python Backend
   SDK; production/dev configuration, themed auth pages, JWT verification,
   principal dependency, `GET /me`. Tests: forged/expired/wrong-origin token,
   sign-in/out, password reset, API 401/403.
2. **Tenant schema and legacy migration:** add org/workspace/role tables and
   ownership FKs; migrate `Original org / omkar` in a staging DB. Tests: row
   counts, IDs, published versions, old runs, same-workspace FK rejection.
3. **All API/worker authorization:** scope every route/query, evidence upload,
   browser WebSocket ticket, webhook, OAuth callback, file access, and internal claim.
   Tests: two unrelated orgs with same names/phone numbers; cross-tenant
   list/detail/write/search/download/WebSocket attempts all denied.
4. **Onboarding/member flows:** one-org creation, workspace create/switch,
   invitation/revoke/remove, owner transfer, platform admin/FDE, webhook
   reconciliation. Tests: races, retries, stale Clerk token, revoked membership,
   removal during active call, last-owner guard, out-of-band role change.
5. **Seed and BYO credentials:** starter templates, write-only credential UI,
   provider discovery/runtime injection, Twilio connection scope. Tests:
   repeated seed, ciphertext only, rotation, key absence, redaction, provider
   selection, cross-workspace key isolation.
6. **Calls and production:** browser test, Twilio dial/media, deployment and
   object storage, quotas, logs, backup/restore, smoke tests with two tenants.
   Validate a real call only after offline checks and with test accounts.

For every slice run meaningful unit/integration tests, Alembic upgrade/check on
a restored DB, OpenAPI/client generation, Ruff, dashboard build, and a role/tenant
matrix review. Gate public sign-up until slices 2-5 pass. Keep a feature flag to
disable new onboarding independently of staff access during rollback.

## Dependencies and decisions to resolve

- Explicit initial platform admin Clerk user ID and the Clerk application to use.
- Confirm FDE's allowed call spending and whether they may set/rotate customer
  provider keys; current proposal says yes with audit, never read raw values.
- Confirm whether org admins may grant other org admins; this plan says yes.
- Confirm provider cost and quota numbers before `trial`/`standard` activation.
- Confirm public deployment host/domain and whether existing local SIM7600
  endpoints should stay private to `Original org / omkar`.

## Verified external references (2026-09-27)

- [Clerk Organization mode and limits](https://clerk.com/docs/guides/organizations/configure)
- [Clerk Organization creation and switching](https://clerk.com/docs/guides/organizations/create-and-manage)
- [Clerk roles and permissions](https://clerk.com/docs/guides/organizations/control-access/roles-and-permissions)
- [Clerk invitations](https://clerk.com/docs/guides/organizations/add-members/invitations)
- [Clerk Python backend guidance](https://clerk.com/articles/how-to-add-authentication-to-a-python-backend)
- [Clerk current plan limits](https://clerk.com/pricing)
- [Twilio Voice JS SDK](https://www.twilio.com/docs/voice/sdks/javascript)
- [Twilio Media Streams](https://www.twilio.com/docs/voice/twiml/stream)
