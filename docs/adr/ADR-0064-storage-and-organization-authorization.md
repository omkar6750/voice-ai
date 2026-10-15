---
id: ADR-0064
title: Keep storage credentials separate from organization authorization
status: Accepted
date: 2026-10-15
related: [ADR-0031, ADR-0044]
---

# Decision

FastAPI remains the public authorization boundary. Clerk authenticates users;
the API checks membership or a valid platform-owner support session and scopes
database access to one organization. Support sessions expire after thirty minutes
and are audited. They do not require a Supabase service key. Recording and artifact
access remains blocked in support mode.

The current private Storage adapter uses a server-only Supabase service key.
This bypasses Storage RLS; it does not grant a dashboard user organization access.
The API still checks resource ownership before reading or writing an object.
Never expose this key to the dashboard or use it as a platform-owner credential.

Production currently relies on application tenant guards and database relationship
constraints. The main organization-owned tables do not have tenant-filtering RLS.
Some other tables have RLS with unrestricted policies for the server role. Direct
`anon` and `authenticated` SELECT access is revoked on the inspected main tables.
This is not equivalent to database-enforced organization isolation.

# Follow-up

Add organization-scoped database RLS as defense in depth using transaction-local,
server-verified organization context and a database role that cannot bypass RLS.
Cover background jobs and audited support sessions, and test pooled-connection
context cleanup and cross-organization denial before deployment.

A restricted Storage adapter would separate its project API key from its bearer
identity and enforce bucket, object-prefix and operation policies. Interactive
Clerk identities alone do not cover background uploads, retention jobs or support
access: design a scoped server identity or storage broker for those operations.
Keep private buckets, object checksums and ownership checks. Do not replace the
service key with an anonymous key without implementing that authorization path.

These follow-ups are not implemented by this ADR. No policies or credentials are
changed by documenting the current boundary.
