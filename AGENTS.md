# Voice AI agent guide

This repository builds a Windows-native voice agent: a FastAPI control plane, a
Pipecat runtime, SIM7600 telephony, PostgreSQL, and a Vite dashboard.

## Start here

- Before structural changes, read [PLAN-0001](docs/plan/PLAN-0001-initial-foundation.md).
- For current project state, read [MEMORY.md](MEMORY.md) and [DECISIONS.md](DECISIONS.md).
- For runtime/configuration/evidence work, read [RFC-0003](docs/rfc/RFC-0003-configurable-runtime.md),
  [ADR-0006](docs/adr/ADR-0006-versioned-configuration.md),
  [ADR-0007](docs/adr/ADR-0007-exchanges-and-integration-secrets.md), and
  [PLAN-0003](docs/plan/PLAN-0003-configurable-runtime.md).
- Read the relevant code and tests before editing. Follow [.tessl/RULES.md](.tessl/RULES.md).

## Toolchain

- Python is pinned to 3.12. Use `uv run ...`; bare `python`, `python3`, and `pip` are unavailable.
- Use Node 24 for `apps/dashboard` and Docker Compose for PostgreSQL.
- Common checks: `uv run pytest`, `uv run ruff check .`, `uv run ruff format .`.
- API: `uv run uvicorn voice_api.main:app --reload --port 8000`.
- Dashboard: from `apps/dashboard`, run `npm run dev` (Vite uses port 5173).
- Database: `docker compose up -d db`, then `uv run alembic upgrade head`.
  The default host port is 55432; use 55433 if 55432 is occupied and keep the
  database URL in sync.

## Architecture boundaries

- `apps/api/voice_api` owns HTTP, settings, database sessions, models, schemas, and services.
- `packages/voice_runtime/voice_runtime` owns Pipecat pipeline construction and call execution.
- `packages/voice_runtime/voice_runtime/telephony` owns modem protocols and adapters.
- `apps/dashboard` is a thin client. Prefer generated OpenAPI types over duplicate DTOs.
- Business code depends on local protocols; keep vendor SDK imports behind adapters.
- Keep changes small. Add an ADR when a new settled architectural choice is not obvious from code.

## Security and runtime rules

- Never commit provider keys, runtime tokens, `.env` files, credentials, or generated call audio.
- Dashboard requests use a short-lived Clerk token from `getToken()`. The dashboard must
  never receive provider keys, encrypted secrets, or runtime credentials.
- Runtime ingestion/control writes use `X-Voice-Runtime-Token` with
  `VOICE_RUNTIME_SERVICE_TOKEN`; this token is separate from dashboard access and stays server-side.
- Provider credentials belong in developer/deployment environment configuration.
- Dashboard action secrets are write-only Fernet-encrypted values.
- `contracts/` and published configuration revisions are authoritative for configurable agents.
  Published versions are immutable; drafts use revisions/concurrency checks.
- `scripts/demo_call.py` is tested reference material. Do not edit it unless the user explicitly asks.
- The API control plane, not Pipecat's runner, is the public control boundary.

## Dashboard guidance

- Follow [docs/design.md](docs/design.md) and the applicable RFCs.
- Use Tailwind v4 and CLI-installed shadcn/ui components. Run
  `npx shadcn@latest add <component>` from `apps/dashboard` for new primitives.
- Keep `apps/dashboard/src/styles.css` limited to theme tokens and Tailwind directives.
  Do not add CSS modules, inline styles, or handwritten component CSS.
- Mark controls pending when the live runner does not yet apply their settings.
- Do not use browser automation for dashboard work unless the user explicitly changes that rule.

## Pipecat guidance

Use the local Pipecat Context Hub before relying on memory for Pipecat symbols,
examples, or deprecations. The CLI entry point is `uv run pipecat context-hub ...`.
Use `uv run ruff`, `uv run pytest`, Pipecat logs, and Context Hub for pipeline
debugging. Real modem/provider checks require hardware and API keys.

## Git and worktrees

- Never rebase; merge instead.
- Work directly on `main` when the user designates a root architecture refactor.
- Otherwise use one lowercase, hyphenated worktree per unit of work and stage files explicitly.
- Use `scripts/worktree.py` for worktree lifecycle when appropriate. Clean up stale worktrees
  and branches after their work is merged.

## Before handing off

Run the narrowest relevant tests and lint checks, inspect the diff, and report any
unverified hardware/provider behavior. Preserve unrelated user changes.

# Agent Rules <!-- tessl-managed -->

@.tessl/RULES.md follow the [instructions](.tessl/RULES.md)
