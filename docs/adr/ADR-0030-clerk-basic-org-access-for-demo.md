---
id: ADR-0030
title: Clerk basic organization access for the first hosted demo
status: Superseded by ADR-0031
date: 2026-09-28
related: [ADR-0028, RFC-0014, PLAN-0038, PLAN-0039]
---

# Decision

> Historical decision only. ADR-0031 and PLAN-0040 make Clerk Organization
> the sole customer tenant. Do not implement the nested tenant model below.

For the first hosted demo, Clerk handles verified email/password identity,
organization membership, emailed organization invitations, and its built-in
`org:admin` / `org:member` roles. No OAuth, custom Clerk roles, separate
workspace-invitation email system, or FDE role is required. Do not prefill or
bootstrap authorization from a human email address. Pin the platform
administrator to an actual verified Clerk user ID after that person signs up.

An organization has multiple application workspaces. Every current member of
an organization can access every workspace in that organization. The server
still checks the member's current Clerk organization membership and each
resource's stored `workspace_id` on every request. A workspace selector is
navigation, not an entitlement. Organization invitations alone give the
recruiter access to the existing `Original org` / `omkar` workspace after
acceptance. Existing members are not re-invited per workspace.

One local `platform_admin_user_id` grants the founder cross-organization
administration. It is not a Clerk organization role and cannot be granted by
customer admins. A local owner ID identifies the org creator for ownership
transfer and the one-owned-organization rule. The owner must also hold Clerk
`org:admin`. Other admins use Clerk `org:admin`; members use `org:member`.
The platform admin can inspect and enter every org/workspace; that override
must be explicit, server-side, and audited. No generic email-based override.

The application keeps a local `users` projection keyed by Clerk user ID for
relationships, names, and audit display. Clerk retains passwords and session
management. The API uses current membership/role for authorization rather
than trusting a copied email, stale UI state, or client-selected org ID.

SIM7600 and the protected local demo remain in source. Hosted Render does not
offer the physical COM device: invoking a SIM-only operation there returns a
clear unavailable error; no SIM code is removed in this slice.

# Supersession

This narrows ADR-0028 and PLAN-0038 where they propose explicit workspace
grants, workspace invitation emails, FDEs, and extra workspace roles. Those
features are deferred, not silently simulated with Clerk invitations.
