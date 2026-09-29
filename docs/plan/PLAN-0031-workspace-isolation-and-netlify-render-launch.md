---
id: PLAN-0031
title: Workspace isolation and one-process Netlify/Render launch
status: Superseded by PLAN-0033
date: 2026-09-28
related: [ADR-0020, ADR-0021, RFC-0014, PLAN-0030]
---

# Decision and scope

> Historical plan only. PLAN-0033 is the sole implementation plan for the
> current org-only product. The second tenant layer and its routes, grants,
> invitations, and roles below must not be built.

For the first hosted demo, follow PLAN-0032 and ADR-0022. In particular,
workspace grants, workspace invitation email, and FDE roles below are no
longer in the demo scope. This older plan is retained for historical context.

This is the concrete delivery plan for the selected topology. It narrows
PLAN-0030's broader product roadmap; it is not a claim that tenancy or deployment
already exists.

- Netlify hosts only the built React/Vite dashboard.
- One Render web service runs FastAPI and the bundled `voice_runtime` package in
  one process, with one Uvicorn worker and one Render instance initially.
- PostgreSQL/pgvector is the durable tenant and run store. Clerk proves identity
  and organization membership. FastAPI authorizes every workspace operation.
- Keep the Pipecat protobuf WebSocket browser-test transport from ADR-0021.
  Twilio uses its existing signed HTTP callbacks and media WebSocket. Browser and
  Twilio share one global active-call slot; there is no call concurrency at launch.
- Do not run SIM7600 COM-port code on Render. Preserve it and the protected demo
  for a separate local hardware branch/workflow. Do not edit `scripts/demo_call.py`.
- Callback scheduling, calendar booking, automatic callbacks, FDE support access,
  and billing are not launch-critical. Preserve historical rows/configuration,
  but hide/disable their live actions until separately completed and tested.
- Org/workspace onboarding, invitations, workspace isolation, seeded tools,
  workspace credentials, browser calls, and Twilio calls *are* launch scope.

No separate runtime server, internal HTTP loopback, Socket.IO, WebRTC media port,
or runtime-service bearer token is needed for this deployment.

# Plain-language runtime boundary

The previous browser/Twilio/SIM code called `http://runtime.local/api/...` or
`localhost:8000` from inside the same Python process. That request went through
HTTP routing/auth only to reach its own database code. The current
`services/local_runtime_service.py` removed the HTTP hop but still imports
endpoint functions. That is transitional, not the final design.

Extract evidence ingestion, run claim/progress, artifact registration, and
applicable action logic into `apps/api/voice_api/services/`. The API route
should validate/authenticate external requests and call the service. The
in-process Pipecat host calls the same service directly with a trusted
`RunContext(run_id, workspace_id)`, not a forged user token. After verifying
there is no remote-worker consumer, remove worker-only HTTP routes,
`ApiEvidenceIngestor`, `VOICE_RUNTIME_SERVICE_TOKEN`, and their dependencies.
Keep actual public APIs: authenticated dashboard operations, the ticketed
browser WebSocket, and signature-verified Twilio/Clerk webhooks. Remove the
unused `/api` compatibility alias before public launch after client cutover.

# Identity and ownership invariants

For launch, configure Clerk for email/password sign-up and sign-in, verified
email, required first and last name, and password recovery. Do not enable
Google/OAuth, seed a default user email, or place any email address in an
authorization allowlist. Clerk stores passwords and owns sessions. The
application stores user profile/membership projections, not credentials.

1. A Clerk Organization maps one-to-one to a local `organizations` row.
   `workspaces` belong to an organization. There are no personal data rows.
2. Clerk owns verified user identity, session, org membership, and invitation
   delivery. The application owns workspace membership, the one-owner rule,
   staff privileges, and resource authorization. Never trust a slug, active-org
   claim, or client-supplied workspace ID without checking current membership.
3. `organizations.owner_clerk_user_id` is non-null and UNIQUE. Thus one user
   can own at most one org. `organization_creation_claims.clerk_user_id` is a
   permanent primary key, so a creator cannot create a second org after
   transfer/archive. Configure Clerk's creation limit to one as an additional
   check, not the only check. Disable generic org creation UI that can bypass
   the application claim.
4. Users may accept invitations to many other orgs as members/admins. An
   invitation never grants ownership. A deliberate ownership transfer may
   name only an active member who owns no org; the previous owner becomes an
   admin/member and retains their lifetime creation claim. A user who already
   owns an org cannot become owner of an invited org.
5. Use Clerk `org:admin` and `org:member` for org membership. Local
   `workspace_memberships` have `admin`, `editor`, `viewer`. Owner and org
   admin inherit access across their org; an ordinary member needs an explicit
   workspace grant. Server-side capabilities, not hidden buttons, enforce this.
   FDE/platform roles in ADR-0020 are deferred, not silently implemented.
6. An owner transfer and Clerk membership change cross systems: lock local
   rows, check invariants, call Clerk, record a pending/success/failure
   operation, and reconcile safely. Never commit two owners or leave an org
   ownerless. Webhooks are verified and idempotent. A stale Clerk token does
   not authorize against revoked server-side membership.
7. Clerk's existing development setting uses organization membership required.
   Prove that its `choose-organization` session task permits the custom
   no-invitation create-org flow. If it does not, adjust the Clerk onboarding
   mode before launch while keeping all product data org-only. Do not assume
   the current sign-up component already provides this flow.

# Tenant schema migration

Add `models/tenancy.py`: `users`, `organizations`, `organization_creation_claims`,
`workspaces`, `workspace_memberships`, `workspace_invitations`, and
idempotent `tenant_events`/`ownership_transfers`. Add workspace-scoped
`provider_credentials`. Add `contact_lists` and `contact_list_entries`;
both are workspace-owned, and each entry must point to a contact in the same
workspace. The existing flat contacts view must also be workspace-filtered.

`users` is a local projection keyed by immutable, unique `clerk_user_id` with
primary verified email (display/contact only), first name, last name,
created/updated timestamps and deactivation state. Do not use email as a
foreign key, proof of identity, or entitlement; it can change. Create/update
the projection idempotently from verified Clerk webhooks and reconcile it on
authenticated `GET /me` so a delayed webhook cannot block onboarding.
Never persist password hashes, session tokens, or raw JWTs. Link owner,
workspace membership, creation claims, and invite audit to this local user
where possible, while retaining Clerk IDs needed for provider calls.

Add `workspace_id NOT NULL` to every tenant data table, including children:

| Model files | Tables to scope |
| --- | --- |
| `models/configuration.py` | `workspace_settings` (replace singleton ID), `agents`, `agent_versions`, `tools`, `tool_versions`, `agent_version_tools`, `contacts` |
| `models/knowledge.py` | `knowledge_bases`, `knowledge_sources`, `knowledge_chunks`, `agent_version_knowledge` |
| `models/integrations.py` | `integration_connections`, `integration_secrets`, `integration_media`, `inbound_webhook_messages`, `calendar_integrations`, `calendar_integration_secrets`, `calendar_oauth_states` |
| `models/evidence.py` | `runs`, `calls`, `browser_sessions`, `exchanges`, `conversation_messages`, `trace_spans`, `tool_invocations`, `callbacks` |
| `models/operations.py` | `flow_node_visits`, `tool_invocation_results`, `tool_context_deliveries`, `classifier_results`, `classifier_context_deliveries`, `interruption_events`, `run_diagnostics` |
| `models/analysis.py` | `classifications`, `context_summaries`, `contact_facts` |
| `models/artifacts.py` | `run_artifacts` |

`runtime_endpoints` describes local physical modems, not customer data. Leave
it out of the Render customer API; isolate it in the local SIM branch or mark
it platform-owned. Identity/catalog tables (`organizations`, `workspaces`,
staff, and the code-owned seed manifest) are intentionally not workspace
children. Inventory any additional tables created by newer migrations before
writing the migration; this list is based on the current worktree models.

Use `(id, workspace_id)` unique keys on tenant parents and composite foreign
keys on cross-resource links, including agent-active-version, agent/tool
bindings, agent/KB bindings, run/contact/version, call/run/contact/Twilio
connection, callback/contact/version/calendar, tool invocation/version,
integration secret/media/connection, and evidence parent/child links. Preserve
existing run-level ordering and publication guards. Validate workspace IDs
embedded in JSONB config at publish and snapshot resolution; relational FKs
cannot inspect JSONB references. Do not trust a copied `workspace_id` in a
request body. Scope ordinary uniqueness as `(workspace_id, normalized_value)`
for agent/tool/KB names, integration labels, contact phone, and list names.
Public provider IDs remain globally unique where required, while stored
records retain a workspace owner.

Migration sequence: (1) merge latest `main` into the worktree (never rebase),
inspect migration head and dirty changes; (2) backup/restore a production-like
DB and record row counts, published IDs, run/evidence/artifact links; (3) add
tenancy tables and nullable `workspace_id`; (4) create the Clerk `Original
org` only after the owner has a verified Clerk user ID, then local workspace
`omkar`; (5) backfill roots and derive each child from its parent, rejecting
ambiguous/orphan cross-links; (6) update all readers/writers and enforce
composite constraints/NOT NULL; (7) remove singleton and global uniqueness
assumptions. Preserve every existing resource ID and historical evidence.
Do not rewrite published configurations just to add a display label.

# Authorization and API contract

Create a typed `Principal` and `WorkspaceContext` in `core/security.py` and
`api/deps.py`. Resolve a workspace from the URL, verify the Clerk session,
load the local org/workspace, check current org membership and workspace grant,
then check a capability. Filter **both lists and individual lookups** by
`workspace_id`; return 404 for another tenant's object. Staff access, when
eventually added, needs an explicit audited support context.

| Existing endpoint families | Required action |
| --- | --- |
| `agents.py`, `tools.py`, `knowledge.py` | Scope listing, get, draft, publish, activate, search, upload and bindings; reject cross-workspace version/KB/tool IDs |
| `contacts.py`, contact timeline and new lists | Scope contacts, phone lookup, facts, imports, search and list membership; no global phone lookup leakage |
| `integrations.py`, `calendar.py`, `providers.py`, `workspace.py` | Scope connections, credentials, model/key status and settings; provider catalog must not reveal another workspace's keys |
| `runs.py`, `calls.py`, `browser_sessions.py`, `dial_catalog.py` | Scope creation, versions, numbers, detail, timeline, ticket, socket, hang-up and downloads |
| `evidence.py`, `analysis.py`, `artifacts.py` | Scope read routes; move same-process writes into services; authorize file and range/download paths |
| `callbacks.py`, `reconciliation.py`, `execution.py`, `telephony.py` | Disable launch-deferred callback/modem routes on Render; bind Twilio callbacks/media to the stored workspace/run via signed provider identity |

Add `GET /me` with allowed orgs/workspaces and effective capabilities.
Add org create/list, workspace create/list/select, members/invitations,
workspace assignment, owner transfer, provider-key metadata/write/test,
contact-list CRUD, and signed Clerk webhook routes. Route naming may remain
under `/api/v1` but every resource handler must take a resolved workspace
dependency. Do not expose the old generic owner gate to customers.

Launch capability matrix:

| Actor | Workspace data | Calls | Secrets | Membership |
| --- | --- | --- | --- | --- |
| Org owner | All workspaces, edit/publish | Browser + Twilio | Add/rotate, never read | Create workspaces, invite/remove, make admins, transfer ownership |
| Org admin | All workspaces, edit/publish | Browser + Twilio | Add/rotate, never read | Create workspaces, invite/remove non-owner members |
| Workspace admin | Assigned workspaces, edit/publish | Browser + Twilio | Add/rotate for assigned workspace | Assign existing org members to assigned workspace |
| Workspace editor | Assigned workspaces, edit/publish | Browser + Twilio | No write | No |
| Workspace viewer | Assigned workspaces, read | No | Metadata only | No |
| Unassigned org member | No workspace data | No | No | No |

New API surface (all `/api/v1`; use opaque IDs in paths and reauthorize
every object):

| Routes | Behavior |
| --- | --- |
| `GET /me`, `GET/POST /orgs` | Accessible orgs and one-org creation claim |
| `GET/PATCH /orgs/{org_id}`, `GET /orgs/{org_id}/members` | Org profile and members |
| `POST/GET/DELETE /orgs/{org_id}/invitations[/{id}]` | Invite intent, list, revoke |
| `PATCH/DELETE /orgs/{org_id}/members/{user_id}` | Admin change/removal with owner guard |
| `POST /orgs/{org_id}/ownership-transfer` | Owner-only transfer to eligible member |
| `GET/POST /orgs/{org_id}/workspaces`, `GET/PATCH /orgs/{org_id}/workspaces/{ws_id}` | Workspace create/select/settings |
| `GET/POST/PATCH/DELETE /orgs/{org_id}/workspaces/{ws_id}/members[/{user_id}]` | Workspace grants |
| `GET/POST/PATCH/DELETE /orgs/{org_id}/workspaces/{ws_id}/contact-lists[/{id}]` | Named lists; item add/remove checks same-workspace contact |
| `GET/PUT/DELETE /orgs/{org_id}/workspaces/{ws_id}/provider-credentials[/{provider}]` | Safe metadata and write-only rotation |
| Existing agent/tool/contact/run/browser/Twilio URLs | Initially retain URLs but require resolved workspace context; move to canonical paths after client generation |
| `POST /auth/clerk/webhook` | Signature-verified, idempotent membership/invite reconciliation |

Keep Twilio callback/media URLs provider-facing, but resolve the workspace
from the signed provider event and stored connection/correlation ID. API
responses never contain another workspace's existence or secret status.

The app-created-org operation reserves a permanent creation claim before
calling Clerk, then stores Clerk org ID + initial workspace + seed state
idempotently. Reconcile a Clerk success followed by DB failure; do not create
an additional org on retry. Invite acceptance verifies Clerk membership and
the stored invitation intent before granting workspace access. Removal and
ownership transfer revoke grants promptly even if webhooks are delayed.

## Invitation contract for the demo

Clerk has **organization** invitations, not a separate workspace invitation
product. An owner/admin can invite an email to an org via Clerk, with a chosen
role and optional workspace assignment intent stored in our database. Clerk
sends the email and handles the invitation ticket. The invitee follows the
link, signs up with the invited email if new or signs in if existing, and
accepts the org invitation. A currently signed-in user can complete the
invite flow without entering credentials again, but the existing session
alone must not grant workspace access. Resolve accepted Clerk org membership
and the invitation's intended email/user, then grant only the selected
workspace(s). Provide an org-only invite option with no workspace grant.
Use an app redirect only after implementing and testing the Clerk ticket
acceptance page; otherwise use Clerk's default acceptance flow and redirect
into the workspace picker after membership reconciliation. Do not assume a
normal JWT is interchangeable with an invitation ticket.

For an **existing member of that org**, adding them to a workspace is a local
workspace-membership operation; do not send a second Clerk org invitation.
The initial demo UI may call this "Add to workspace" and show immediate
access. A separate emailed workspace-only invitation/notification requires
an application mail delivery path and is not supplied by Clerk org invites;
do not present it as implemented. The UI shows pending org invitations,
supports revoke, and rechecks membership before any workspace grant.
Invitation metadata may help correlation but cannot itself authorize access.
Use Clerk user ID and verified current membership as the final identity check.

Dashboard routes/components to add in `apps/dashboard/src/app/` and
`src/pages/`: public landing/sign-in/sign-up; invitation acceptance;
no-invitation create-org + first-workspace onboarding; org/workspace selectors
in the shell; org members/invitations/ownership settings; workspace
members/credentials/Twilio settings; workspace-scoped agents, seeded tools,
contacts and named lists; browser test and run detail. The existing
`App.tsx` legacy-owner gate is replaced only after all API routes are
workspace-scoped. Generate TS contracts from the new OpenAPI, and show
capabilities from `GET /me` rather than hard-coding role assumptions in UI.

# Seeded tools and starter agents

Keep a reviewed, versioned system-tool **manifest in code**, not shared mutable
customer tool rows. On each new workspace creation, transactionally import
workspace-owned `tools`/`tool_versions` and starter `agents`/`agent_versions`
with bindings to that workspace's copies. Record manifest version and source
key on imported rows; repeated onboarding is idempotent. A seeded tool may
show as unavailable until that workspace has the required integration/key.
Users can edit or duplicate drafts without changing other workspaces. Updates
offer new copies/versions and never overwrite published or customer-edited
versions. Migrate `Original org / omkar` existing agents and tools without
re-seeding or losing IDs. Test that a workspace's agent cannot bind another
workspace's system-tool copy, including IDs embedded in JSONB.

# Calls, storage, and credentials

Use one durable `active_call_slot` record for the entire Render deployment,
acquired atomically for both browser and Twilio admission before external
effects. Ticket issue/consume is persisted as a hash, single-use, expiring
record bound to session/workspace; origin is explicitly allowed. Twilio dial
must reserve the slot before dialing. Release only after transport cleanup and
run finalization; uncertain cleanup requires explicit reconciliation, never
blind redial or immediate slot reuse. This replaces the current process-memory
browser-only guard. Each run stores immutable `workspace_id`, selected
agent/contact/version/connection, provider IDs, and safe credential references.
One active call means one combined browser **or** Twilio call, not one of each.

Provider keys and Twilio credentials are encrypted with a Render-side keyring
in workspace-owned rows. UI can add/rotate/test but never read plaintext.
Resolve/decrypt only the selected workspace's required keys at call start;
never serialize plaintext into snapshots, traces, API responses, or browser
bundles. No workspace key means explicit unavailable state. Trial/paid quotas
and staff overrides are separate later features; the global call slot is the
initial safety limit. Recordings, evidence spool and uploaded media must use
workspace-prefixed paths with authenticated downloads. Local disk on a Render
instance is not the final durable artifact store: choose object storage and a
recovery/retention policy before relying on production recordings.

# Netlify + Render implementation

1. Netlify: build `apps/dashboard` with Node 24, publish its `dist`; add
   React Router SPA fallback. Build-time public values: Clerk publishable key,
   `VITE_API_BASE_URL=https://<render-api>` and
   `VITE_WS_BASE_URL=wss://<render-api>`. No secret keys in Vite/Netlify.
2. Dashboard `app/api.ts` and `TestAgentModal.tsx`: use those API/WSS origins
   rather than relative `/api/v1` and `location.host`. Keep Clerk bearer
   tokens on HTTPS requests only; the WebSocket receives a short-lived ticket,
   never a Clerk token in its URL. Correct stale “WebRTC” UI copy.
3. Render: one image/service containing `apps/api/voice_api` and
   `packages/voice_runtime/voice_runtime`; bind FastAPI to `0.0.0.0:$PORT`
   with one worker. Remove dashboard `dist` serving from `main.py` after
   Netlify cutover. Set exact CORS origins for approved Netlify production
   domain(s), exact Clerk authorized parties, and exact allowed WebSocket
   origins. Do not use wildcard origins for credentialed browser access.
4. Use one PostgreSQL/pgvector service with backups and migrations as an
   explicit deploy step. Keep Clerk secret, encryption keyring, provider/Twilio
   credentials, webhook signing keys, and DB URL only on Render. Configure
   Clerk production instance, Netlify callback/redirect domain and verified
   webhooks. Public Render HTTPS/WSS reaches both API and browser/Twilio socket.
5. One process/instance is a deliberate launch limit, not horizontal scaling.
   A later second instance would need shared socket/session state and more
   general dispatch. Render deploy/restart can interrupt a call; finalization
   and recovery must mark it uncertain safely. No live deployment is claimed
   by this plan.

# Ordered delivery and release gates

1. **Separate local SIM demo:** preserve physical COM work on a hardware-only
   branch/worktree after accounting for uncommitted changes; no SIM endpoint
   exposed on Render. A local SIM call is tested there, not in production.
2. **Clean runtime boundary:** extract endpoint business code into services,
   remove worker-only routes/token and callback tools from launch exposure,
   retain browser WebSocket and signed Twilio external routes. Test no
   localhost/ASGI loopback or endpoint imports from service layer.
3. **Tenancy schema and data backfill:** restored-DB migration with count,
   ownership, published-version, tool-binding and historical-run proofs.
4. **API authorization:** every route, WebSocket, download, search, callback
   and background action gets a workspace policy; cross-tenant matrix passes.
5. **Onboarding/seed/credentials UI:** create one org/default workspace,
   invite/accept/remove, workspace picker, ownership transfer, starter agent
   and tools, contact lists, write-only keys, Twilio connection/number picker.
6. **Production transport and hosting:** Netlify API/WSS origin, Render
   single-worker service, durable global call slot, artifact storage/recovery,
   Clerk production redirect configuration, provider signatures and CORS.
7. **End-to-end gates:** two unrelated orgs with identical agent/tool/contact
   names and phone numbers cannot see or bind each other's data; invitees see
   only assigned workspaces; creator cannot create/own a second org; transfer
   cannot create two owners; repeated seed changes nothing; browser and Twilio
   cannot overlap; a real browser call has audible two-way speech, mute,
   interruption and finalized evidence; a signed Twilio call completes.
   Run migrations, full tests, Ruff, OpenAPI/client generation, dashboard
   build and Netlify/Render smoke tests. Do not open public sign-up to other
   customers before the tenant gates pass.

# Current blockers and explicit non-goals

- Current `main` is ahead of this worktree; merge and inspect it before
  choosing migration revision IDs. Do not overwrite the dirty root checkout.
- Current WebSocket test mocks the Pipecat pipeline and does not prove audio.
  No real browser/Twilio/Render call has been verified in this worktree.
- Current owner mapping is an email until a verified Clerk user exists. Never
  backfill the legacy data to an unverified or guessed user ID.
- Current callback/calendar code and signing key are not required for this
  release. Preserve historical data; do not ask for
  `VOICE_CALLBACK_SLOT_SIGNING_KEY` in the launch checklist.
- FDE/platform administration, billing, automatic callbacks, SSO, multi-worker
  dispatch and simultaneous calls are outside this launch slice.

# Source checks

- Clerk organization creation and membership settings:
  https://clerk.com/docs/guides/organizations/configure
- Clerk organization invitations:
  https://clerk.com/docs/guides/organizations/add-members/invitations
- Render WebSocket and instance-routing behavior:
  https://render.com/docs/websocket
- Netlify Vite and SPA deployment:
  https://docs.netlify.com/build/frameworks/framework-setup-guides/vite/
