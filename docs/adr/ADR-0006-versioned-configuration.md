---
id: ADR-0006
title: Immutable published configuration and explicit bindings
status: Accepted
version: 1
date: 2026-09-22
related: [RFC-0003]
---

Use typed JSONB for configuration and relational foreign keys for ownership,
tool bindings and knowledge bindings. PostgreSQL guards published content and
bindings. Activation is separate from publishing. Pydantic defines public
contracts; generate TypeScript from OpenAPI. Knowledge remains mutable; exact
retrieved passages live in invocation evidence, without corpus version history.
