---
id: ADR-0031
title: A Clerk Organization is the only customer tenant
status: Accepted
date: 2026-09-28
related: [PLAN-0040, ADR-0028, ADR-0030, RFC-0014]
supersedes: [ADR-0028, ADR-0030]
---

# Decision

Each Clerk Organization is one customer account and owns its agents, tools,
contacts, knowledge, integrations, encrypted credentials, calls, and evidence.
There is no second application tenant below it. Clerk owns user identity,
sessions, org membership, emailed invitations, and the built-in Admin/Member
roles. FastAPI checks current membership and capability on every operation,
then scopes every persisted object by `org_id`. The frontend's active org,
URL, or token claim alone never grants access.

The API verifies browser session tokens with the official Clerk Python Backend
SDK `authenticate_request_async` and authorized-party validation. Current org
memberships, invitations, and roles are read or changed through the SDK Backend
API resources. FastAPI dependency injection is the request guard (the Python
SDK does not supply FastAPI-specific middleware). Application-specific route
access is explicit: member-safe product routes opt in with
`@allow_organization_member`; all other guarded product routes require an org
admin. The request dependency verifies that the active Clerk organization has
a local catalog row, verifies membership live through Clerk, and binds the
corresponding local `org_id` before resource access. Original-only legacy
operations use an additional legacy-org check. This is separate from Clerk
authenticating the session and reporting the current organization role.
The same gate rejects a locally disabled user even if their Clerk session and
live organization membership remain valid during revocation propagation.

The application database owns the user profile/audit projection, local org
mapping, one-organization creation claim, single owner invariant, and one
platform-admin assignment. The platform admin's Clerk user ID is recorded
only after identity verification, in a DB assignment—not an environment
variable or email fallback. The reported initial candidate is
`user_3Jx1ULmJ2F8pxqsAYyM8aWT48Or`; its actual Clerk user and org
membership must be verified before any DB grant. The existing Clerk org is
adopted by immutable Clerk ID, not recreated from its display name.

For launch, org members can read and browser-test, org admins can configure
and manage members, the owner can transfer ownership, and the sole platform
admin can enter all orgs with an audit trail. No FDE or custom Clerk roles.
The recruiter is invited to the existing org using Clerk's standard email;
there is no other invitation or membership mechanism.

Platform support entry is explicit, not inferred from a session claim. A
platform admin starts a 30-minute session for one registered org; the API
stores only a hash of the random token, verifies the DB platform assignment
and session on each scoped request, and records start/end in organization
audit. Starting another session revokes the prior active one. The dashboard
keeps the token in memory, sends it only as a request header, and disables
Twilio dialing while support mode is active. Clerk session verification remains
required throughout.

The unused nested catalog introduced in migration 0026 is retired by a new
migration, without rewriting that applied revision. The old unscoped data is
backfilled to the verified existing org in the isolated DB with all IDs,
published versions, ciphertext, and evidence preserved. Do not enable
organization creation for general customers until the API/RBAC, runtime,
WebSocket, callback, file, and background-job boundaries are audited and the
end-to-end two-org flow is verified. Organization creation is feature-flagged;
the isolated suite proves ORM/Core isolation, same-org FK enforcement, and
registered-org scope binding, but is not the full launch audit.

Tenant-owned rows require a non-null `org_id`. Customer-facing uniqueness for
agent/tool/knowledge-base names, integration labels, and contact phone numbers
is scoped to the organization. Database guards reject single-column foreign
key references between tenant-owned rows when their organizations differ;
schema-discovered tenant columns are required. Application scopes still must
filter every read and validate non-FK references.

# Consequences

Routes and pages use `/orgs/{org_id}/...` with no additional tenant prefix.
Provider keys, Twilio connections, contact lists, seed copies, run snapshots,
and artifact paths belong to an org. This reduces onboarding and invitation
steps, but means all members of an org share the same data boundary; finer
team isolation would require a new explicit decision and schema later.

Netlify hosts the dashboard. The API and Pipecat runtime now have separate
Render service images; the API remains the public control boundary. Preserve
the browser WebSocket, Twilio path, and local SIM code. Hosted SIM attempts
fail clearly when hardware is unavailable.

## 2026-10-04 ownership amendment

`org:admin` and `org:member` are the only intended Clerk roles after the
development instance is reconciled. A temporary `org:owner` membership is
accepted as admin-equivalent during that conversion, never as proof of product
ownership. An enabled local user is the product owner only when their ID
matches `organizations.owner_user_id` and Clerk confirms current admin
membership in that organization. Context and resource access use live
membership, not a stale token role. An unregistered Clerk organization may
become locally owned only by Clerk's recorded creator. The independent
`PlatformAdministrator` assignment remains the sole platform authority.
The exact cutover and unfinished transfer workflows are recorded in
`docs/plan/PLAN-local-ownership-with-clerk-basic-roles.md`.
