---
id: RFC-0014
title: Clerk authentication, customer organizations, workspaces, and production access
status: In progress
version: 1
date: 2026-09-27
related: [RFC-0003, RFC-0004, ADR-0020, PLAN-0030]
---

# Problem and scope

The current control plane uses one operator bearer token and one settings row.
Agents, tools, contacts, knowledge, integrations, runs, and media are not tenant
scoped. That is sufficient for local operation but cannot safely serve invited
customers. This RFC defines the user-facing contract and the migration boundary.
ADR-0020 settles identity and authorization ownership; PLAN-0030 maps routes,
models, implementation slices, and verification gates.

The new Clerk development app is `Voice AI B2B`, application ID
`app_3Jutc4GvIX2mItzJoPGOxccUsYi`. Organizations are enabled with forced
selection and up to 20 members. A production instance and domain are pending.
Development keys are in ignored `.env.local` files, never in source or docs.

# User journeys

## Public entry and identity

The public landing page provides Sign up and Log in. Clerk handles email
verification, sign-in, sign-out, password recovery, session renewal, and the
user profile. The application never handles passwords. Invite recipients are
sent to a Clerk acceptance flow and then to the relevant workspace. A new
signed-in user without an invitation is prompted to create one organization
and one initial workspace. Organization membership is required; there is no
personal data namespace.

An existing member sees organizations they belong to. A user may join several
organizations but can create only one through this application. A workspace
selector shows only assigned workspaces; org admins and owners see all in their
org. Each URL includes org and workspace identity for navigation, while the
server verifies membership for every API and stored resource lookup.

## Customer management

Org owner invites members, makes org admins, removes members, creates workspaces,
and transfers ownership to an active member. Org admin does the same except
ownership transfer, owner removal, or owner demotion. Workspace admin manages
only an assigned workspace and can invite an org member to it. Editors can
author, publish, test, and place calls. Viewers can inspect but cannot mutate
or dial. The UI shows effective capabilities, and the API enforces them.

Each organization has one owner in application data. Clerk `org:admin` means
administrative membership, not ownership. The transfer endpoint promotes the
recipient in Clerk, changes the local owner under a lock, records an audit
event, and preserves one owner through retry/reconciliation.

## Platform support

Exactly one platform admin is bootstrapped by a verified Clerk user ID. That
admin can invite/revoke FDEs. FDEs can inspect and operate customer
organizations and workspaces through an explicit support context with audit
records. Neither FDE nor customer admin can grant platform roles. The FDE is
not a Clerk Organization role; staff access is checked in PostgreSQL after
Clerk proves user identity. Clerk Dashboard team roles are operational access
to Clerk itself and do not grant application staff privileges.

## Trying the product

A new workspace receives immutable seeded tool definitions and copyable starter
agents with valid bindings. Customers can edit their own copies. Existing agents,
tools, runs, and evidence remain under `Original org / omkar`; the migration
retains their IDs and published versions. Providers show a clear missing-key
state. A customer can add workspace-scoped keys through write-only forms,
verify them, and start a browser agent test. Twilio outbound calls require an
enabled customer Twilio integration and verified from-number. Browser agent
testing uses WebRTC and the customer's AI provider keys; Twilio is not required.

# Contracts and invariants

- `GET /api/v1/me` returns Clerk user ID, active org/workspace, effective
  capabilities, and allowed workspace list. It returns no decrypted secrets.
- Organization and workspace management endpoints, invitation lifecycle,
  provider-key endpoints, and staff endpoints are specified in PLAN-0030.
- Every existing `/api/v1` route is assigned one of: public signed callback,
  Clerk session + tenant capability, worker credential + run scope, or disabled.
  No generic operator-token fallback is exposed to signed-in customers.
- A requested workspace and every referenced agent/tool/contact/integration
  belong to the same workspace. Database constraints protect cross-root links
  where practical; query filters enforce authorization on all reads/writes.
- Provider credentials are encrypted with deployment keys and resolved at run
  start. Snapshots, evidence, logs, and responses carry only safe references
  and status. FDEs may rotate but never retrieve a plaintext value.
- Staff, membership, ownership, credential, and paid call actions are audited.
  Webhooks are verified and idempotent. Background workers use scoped service
  credentials rather than a customer session.
- Public sign-up remains gated until tenant backfill, API scoping, worker
  scoping, and cross-tenant tests pass.

# Rollout and compatibility

Start with the Clerk identity foundation in an isolated worktree. Committed
`main` through `0a7a446` has been merged. Review any further root checkout
changes before choosing migration revision numbers.
Migrate the current DB into one mapped org/workspace without changing resource
IDs. Verify counts, published config, and historical evidence on a restored
database. Add workspace ownership to roots and enforce non-null scope only
after all readers/writers use it. Replace the shared token on external routes;
give workers a separate scoped auth path. Release the landing page and public
onboarding only after the full authorization matrix passes.

The implementation must preserve existing demo and run evidence. Production
requires a Clerk production instance/domain, secrets manager, TLS/WSS, shared
browser-session/worker state, object storage for media, backups, and quotas.
