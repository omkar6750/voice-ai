---
id: ADR-0006
title: Immutable published configuration and explicit bindings
status: Accepted
version: 2
date: 2026-09-23
related: [RFC-0003]
---

Use typed JSONB for configuration and relational foreign keys for ownership,
tool bindings and knowledge bindings. PostgreSQL guards published content and
bindings. Activation is separate from publishing. Pydantic defines public
contracts; generate TypeScript from OpenAPI. Knowledge remains mutable; exact
retrieved passages live in invocation evidence, without corpus version history.

## Schema review amendment

Updated in place at the user's explicit request; RFC-0003 version 2 records all
29 review dispositions and reasons. This is an exception to immutable ADR editing.

Version identifies configuration; revision is the optimistic draft edit counter,
not historical edit versioning. Clone published versions into new drafts with
lineage. All draft/binding writes require the expected revision. PostgreSQL must
guard published versions and bindings, and active versions must be published and
belong to the selected agent. Publishing does not activate.

Keep prompts/flows in typed agent JSONB and exact tools in relational bindings.
No separate prompt releases, deployment tables or historical KB builds. KB owns
ingestion settings; agent owns retrieval settings. Operational ingestion tokens
fence stale work and do not identify retained corpus revisions. Initially enforce
normalized Gemini embeddings at 768 dimensions.

Resolve and hash canonical, credential-free runtime snapshots with schema and
application/dependency identifiers. Hash identifies configuration, not deterministic
provider or mutable-KB replay. Preserve string IDs; use database creation defaults,
query-driven indexes and separate runtime occurrence timestamps.
