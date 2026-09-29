# PLAN-0036 — Remove unused wait settings

Status: Completed (2026-09-29; database application pending)

## Existing facts

- `WaitConfig` allowed `silent_wait` and `acknowledge_then_wait`, but no runtime code read either value or spoke its acknowledgement.
- Plan 2 establishes execution behavior by handler: only callable `classify_lead` runs in the background; entry/exit classifiers, WhatsApp, knowledge retrieval, callback tools, and runtime-control tools remain awaited.
- The tool editor inserted `silent_wait` into every saved payload, the tool detail page displayed persisted values, and API list responses also synthesized a default wait value.
- Tool versions and agent versions store strict JSONB config. Existing published and draft rows may contain obsolete `wait` keys.

## Scope and behavior

- Remove `WaitConfig` and the `wait` fields from `ToolConfig` and `RetrievalConfig`; strict config validation must reject the removed key.
- Add one forward-only migration to remove top-level `wait` from every `tool_versions.config` and nested `retrieval.wait` from every `agent_versions.config`, including published versions. Preserve all other JSON, IDs, version numbers, revisions, statuses, and bindings. Do not rewrite historical run snapshots or evidence.
- Stop synthesizing wait config in API responses and generated WhatsApp/knowledge tool definitions. Remove tool editor injection and tool detail display.
- Explain in tool authoring that handler/runtime code owns execution timing and caller-facing phrasing belongs in the agent prompt or tool description. Do not add another mode selector.
- Regenerate OpenAPI and dashboard types from the Pydantic contract.

## Files and subsystems

- Shared config: `packages/voice_runtime/voice_runtime/contracts/tools.py`, `knowledge.py`, and `contracts/__init__.py`.
- API: tool version listing and built-in WhatsApp/knowledge tool creation; Alembic revision `0029_remove_unused_wait_config.py`.
- Dashboard: tool editor and tool detail page.
- Tests: strict contract tests, migration/data validation where an isolated PostgreSQL database is available, and API/OpenAPI generation checks.

## Tests and acceptance

- Tool and retrieval config reject `wait` as an extra field; ordinary valid configs still validate and resolve.
- Migration removes only the two obsolete JSON keys from draft and published rows while preserving every other value and binding.
- API responses and generated tool configs never synthesize `wait`; dashboard payloads omit it and the details page no longer presents it.
- Generated OpenAPI/TypeScript has no `WaitConfig` or wait property; dashboard TypeScript and production build pass.
- Run focused and full unit tests, Ruff, OpenAPI export, dashboard generation/typecheck/build, and database migration/integration checks when PostgreSQL is available.

## Non-goals

- No `acknowledge_then_continue`, new wait enum, synthetic acknowledgement, or acknowledgement field.
- No change to which handlers are awaited; specifically only callable `classify_lead` is nonblocking.
- No HTTP-tool runtime implementation, demo/seed edits, or historical run/evidence rewrite.

## Manual verification

- Apply migrations and verify all tool-version JSON lacks top-level `wait`, and all agent-version retrieval JSON lacks nested `wait`.
- Load existing drafts and published versions in the dashboard; confirm no wait setting is displayed or reintroduced when saving.
- Place a test call: classifier returns promptly and its result arrives on a later caller turn; WhatsApp, knowledge retrieval, callbacks, and control tools retain their awaited behavior.

## Verification

- Full unit suite and Ruff pass; OpenAPI export, TypeScript generation, and dashboard production build pass.
- Alembic revision `0029_remove_unused_wait_config` renders successfully in PostgreSQL offline SQL mode.
- Database-backed integration tests are unavailable without `VOICE_TEST_DATABASE_URL`; this migration was rendered but not applied to a development database. Apply it during the next database upgrade.
