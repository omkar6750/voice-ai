---
id: ADR-0002
title: Use async SQLAlchemy and Alembic for first database slice
status: Accepted
version: 1
date: 2026-09-21
authored_by: codex
session: voice-ai-foundation-01
supersedes: null
superseded_by: null
related: [RFC-0001]
---

# Decision

Use PostgreSQL with async SQLAlchemy 2 and Alembic. The first migration contains only agents, agent versions, contacts, and calls. The RFC names more entities, but turns, traces, actions, and callbacks wait for a concrete call lifecycle.

# Cost

The project does not use Prisma. This keeps the Python control plane and runtime on one persistence toolchain. A future TypeScript data service would need a new decision.
