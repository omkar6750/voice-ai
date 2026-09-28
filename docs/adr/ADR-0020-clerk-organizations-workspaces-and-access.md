---
id: ADR-0020
title: Clerk identity with application-owned workspaces and authorization
status: Accepted
date: 2026-09-27
related: [RFC-0003, RFC-0004, RFC-0014, ADR-0006, ADR-0007, PLAN-0030]
---

# Decision

The new Clerk development application is `Voice AI B2B`
(`app_3Jutc4GvIX2mItzJoPGOxccUsYi`). This identifier is public configuration;
its credentials remain only in ignored local environment files and the Clerk
account. The development instance has Organizations enabled with forced selection
and a 20-member cap. Production remains unprovisioned.

Build a B2B application. A Clerk Organization is one customer organization. A
PostgreSQL workspace belongs to exactly one organization and owns authoring,
integrations, contacts, runs, evidence, and settings. Users can belong to several
organizations and workspaces, but may create at most one organization through the
application. There is no personal data namespace.

Clerk owns sign-in, password reset, verified identities, organization membership,
and organization invitations. The application owns its workspace membership,
single-owner invariant, platform staff assignments, resource permissions, and
tenant isolation. The API verifies Clerk sessions on each interactive request and
derives the organization and workspace from verified identity plus server-side
membership records. A path, header, or JSON body never grants scope by itself.

The platform has one designated administrator and zero or more FDEs. The platform
administrator can invite/revoke FDEs; FDEs can inspect and operate all customer
organizations/workspaces but cannot grant platform roles, change ownership, or read
stored secret values. Every support action is audited with actor, target, purpose,
and timestamp. Customer organizations have exactly one owner, any number of admins,
and members. Workspace access for ordinary members is explicit; org owner/admin
can access all workspaces in their org. Workspace roles are `admin`, `editor`, and
`viewer`. Customer org roles continue to use Clerk's built-in `org:admin` and
`org:member`; ownership is a separate app invariant, not a Clerk role.

Use custom app pages for organization creation, member management, ownership
transfer, staff invitations, and workspace invitations. Generic Clerk organization
management components can expose paths that bypass the product's one-org and
single-owner rules. Clerk's sign-in, sign-up, user profile, and password reset
components may be embedded and themed.

Provider credentials are encrypted at rest under deployment-managed keys. Their
scope is workspace. Runtime resolution decrypts only the selected workspace's
required keys immediately before use; immutable run snapshots and evidence contain
only provider identity, credential record ID/version, and safe diagnostic metadata.
Secrets never enter browser responses, logs, prompts, or generated configuration.
Twilio credentials and phone numbers follow the same workspace boundary.

The existing single-operator records move together into Clerk organization
`Original org`, workspace `omkar`. Their IDs, versions, bindings, publication state,
run evidence, and historical links stay intact. New customer workspaces receive
copies of approved starter agents and seeded tools; they never share mutable agent
or tool rows across tenants.

# Why

The current `workspace_settings` table is a singleton; roots such as agents,
tools, contacts, knowledge bases, integrations, and runs have no tenant column.
`require_operator` compares a shared token, while browser calls and workers reuse
that token. Enabling public sign-up before changing those paths would expose data
across customers. The current Twilio integration already demonstrates an encrypted
secret record and write-only UI. Reuse its keyring concept with per-workspace
ownership and explicit runtime lookup.

Clerk's production offering includes the default Admin/Member roles, invitations,
and custom permissions; custom organization roles and role sets are an enhanced B2B
feature. Local workspace and staff roles keep the initial product small and avoid
making production access depend on a custom Clerk role. Clerk Organization creation
limits are useful as a second check, while an application ledger enforces the
business rule even after deletion or ownership transfer.

# Consequences and boundaries

- A Clerk session proves identity and active organization membership. The API still
  checks current local membership and resource ownership. Authorization decisions
  are server-side and fail closed during missing/stale mappings.
- Organization create/invite and workspace create/invite use application endpoints.
  Clerk webhooks reconcile outside changes and are idempotent; onboarding does not
  wait for webhook delivery.
- Public provider webhooks, OAuth callbacks, and runtime worker ingestion need
  separate authentication. A user session is never passed to a background worker.
- Published agent/tool versions remain immutable. Tenant migration only adds
  ownership and enforces same-workspace links; starter copies are new versions.
- This ADR supersedes the single-operator and no-tenancy assumptions in RFC-0004
  and ADR-0007 for the production application. It does not rewrite historical
  decisions or authorize editing `scripts/demo_call.py`.

# Open decisions before implementation

1. Confirm the Clerk application, production domain, and initial administrator's
   verified Clerk user ID. Bootstrap cannot use an email string alone.
2. Choose whether FDE can place paid calls or only inspect/configure. The default
   in PLAN-0030 allows calls with an audit trail and workspace quotas.
3. Set launch limits for organizations, workspaces, seats, and call concurrency.
   These are product quotas rather than authentication roles.
