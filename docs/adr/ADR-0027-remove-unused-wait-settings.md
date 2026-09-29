---
id: ADR-0027
title: Remove wait-mode config; execution timing belongs to runtime handlers
status: Accepted
version: 1
date: 2026-09-29
related: [ADR-0006, ADR-0025, ADR-0026]
---

Tool and retrieval wait settings are removed because no runtime path consumed
them. They could make the dashboard appear to control behavior that was actually
determined by each registered handler. Only callable `classify_lead` is
nonblocking; entry/exit classifiers, WhatsApp, knowledge retrieval, callbacks,
and control tools are awaited. Generic HTTP tools remain unsupported for calls.

`WaitConfig` and its fields are removed from the shared strict Pydantic
`ToolConfig` and `RetrievalConfig` contracts. Tool API list responses no longer
synthesize a default wait value. Built-in WhatsApp and knowledge tool creation
no longer persists one. The dashboard does not inject or display the removed
field and explains that runtime handler behavior owns execution timing; the
agent prompt/tool description owns conversational wording.

Alembic revision `0029_remove_unused_wait_config` updates every saved
`tool_versions.config` to remove top-level `wait` and every
`agent_versions.config.retrieval` to remove nested `wait`. It retains all other
JSON keys and does not rewrite historical run snapshots or evidence. The
migration is intentionally forward-only in the development environment.

Verification: full unit suite and Ruff pass; OpenAPI export, dashboard type
generation, and production build pass. Migration `0029` renders successfully in
offline PostgreSQL SQL mode. Database-backed integration tests were skipped
without an isolated test database, and no development database was mutated in
this verification run.
