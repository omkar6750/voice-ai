# Voice AI working agreement

Read [docs/plan/PLAN-0001-initial-foundation.md](docs/plan/PLAN-0001-initial-foundation.md) before structural changes. Read `MEMORY.md`, `DECISIONS.md`, the owning RFC, then relevant code and tests at session start.

## Toolchain

Use `uv run <command>` for Python. Bare `python`, `python3`, and `pip` are broken Microsoft Store stubs on this machine. Python is pinned to 3.12 by `.python-version`. Use Node 24 for the dashboard and Docker Compose for PostgreSQL.

Common commands:

```powershell
uv sync
uv run pytest
uv run ruff check .
uv run ruff format .
uv run alembic upgrade head
uv run uvicorn voice_api.main:app --reload --port 8000
cd apps/dashboard; npm run dev
```

`docker-compose.yml` uses pgvector PostgreSQL. Default host port is 55432. If another
database owns it, set `VOICE_DB_PORT=55433` before `docker compose up -d db`, then set
matching `VOICE_DATABASE_URL` for migrations.

## Boundaries

- `apps/api/voice_api` owns HTTP, settings, database sessions, and relational models.
- `packages/voice_runtime/voice_runtime` owns Pipecat pipeline construction and call execution.
- `packages/voice_runtime/voice_runtime/telephony` owns modem protocols and adapters.
- The standalone demo owns its provider settings and SDK setup. Configurable provider adapters remain pending; do not recreate an empty providers package.
- `apps/dashboard` is a thin client. Generate API types from OpenAPI when API surface grows. Do not hand-maintain duplicate DTO contracts.
- Dashboard sends `Authorization: Bearer $VOICE_OPERATOR_TOKEN` only from browser memory. It never receives provider keys or encrypted secrets.
- STT, LLM, TTS and embedding credentials remain developer environment configuration. Dashboard action integrations use write-only Fernet-encrypted secrets.
- Business code depends on local protocols, not vendor SDKs.
- Keep units small. Add an ADR when a settled choice is not obvious from code.

## Pipecat CLI

The project uses Pipecat CLI from `pipecat-ai`.

```powershell
uv run pipecat --help
uv run pipecat --version
uv run pipecat init --list-options
uv run pipecat init . --dry-run
uv run python scripts/demo_call.py --number +15551234567
```

`pipecat init` is useful for checking current scaffold options. Do not scaffold over this repository because its layout and SIM7600 boundary are deliberate. The local development server for this project is FastAPI on port 8000. Vite runs on port 5173. Pipecat's runner is not the public control plane.

For pipeline debugging, use `uv run ruff`, `uv run pytest`, Pipecat log output, and Context Hub API lookups. Real modem and provider checks require hardware and API keys.

## Pipecat Context Hub

Context Hub is installed through the Pipecat CLI and has a local indexed copy of Pipecat docs, examples, and API source. Use it before relying on memory for Pipecat symbols.

```powershell
uv run pipecat context-hub status
uv run pipecat context-hub search-docs "PipelineWorker"
uv run pipecat context-hub search-api "Sim7600UsbAudioTransport"
uv run pipecat context-hub search-examples "Groq voice pipeline"
uv run pipecat context-hub get-code-snippet --symbol "CartesiaTTSService"
uv run pipecat context-hub check-deprecation "pipecat.pipeline.task.PipelineTask"
uv run pipecat context-hub refresh
uv run pipecat context-hub serve
```

`status` reports index freshness. `search-*` finds current docs and source. `get-code-snippet` retrieves focused code. `check-deprecation` catches moved APIs. `refresh` updates the local index. `serve` starts the MCP server for an agent client. Context Hub data is stored outside this repository under the user profile. `pipecat context-hub install --client codex` can register the MCP server for a fresh agent setup, then restart the agent.

## Configurable runtime

The old voice-agent launcher and duplicate runtime config/pipeline were removed.
contracts/ owns DB-backed agent configuration. API call dispatch uses the fenced
SIM7600 executor and the native Pipecat host, not the protected demo script.
The resolved snapshot drives prompts, provider models, audio, VAD and node bindings.
Finalized transcript, operation/tool/flow evidence and recordings are delivered
under the run ID. Other demo actions and background jobs are not yet connected to
the live runner; unsupported action tools return explicit errors. See PLAN-0003
and PLAN-0004.

Read RFC-0003, ADR-0006, ADR-0007 and PLAN-0003 before changing config, evidence,
knowledge, or integrations. `scripts/demo_call.py` is tested reference material: do not edit it
without explicit user instruction. Agent/tool drafts use revisions; published versions are immutable.

## API Architecture

Dashboard work follows RFC-0004 through RFC-0013 and docs/design.md. Use Tailwind v4 utilities and CLI-installed shadcn/ui components. `apps/dashboard/src/styles.css` holds the required shadcn theme tokens and Tailwind directives only; do not add handwritten component CSS, inline style attributes, or CSS modules. Run `npx shadcn@latest add <component>` from `apps/dashboard` for new primitives. Keep operator token in browser memory, generate typed API contracts as response models become available, and mark controls pending when the live runner does not apply their settings. Do not use browser automation for this dashboard task unless the user changes that instruction.

`apps/api/voice_api` follows a layered structure:
- `core/`: Application settings (`config.py`), security and credential sanitization (`security.py`).
- `db/`: Declarative base (`base_class.py`), engine and session factory (`session.py`), and model aggregator for migrations (`base.py`).
- `models/`: SQLAlchemy relational ORM models.
- `schemas/`: Pydantic validation and serialization models.
- `api/`: API dependency injection (`deps.py`), `v1/api.py` router aggregation, and `v1/endpoints/`.
- `services/`: Business logic services (call orchestration, configuration resolution, publications, evidence, artifacts, knowledge, vault, integrations).

## Git & Worktree Conventions

- **Never rebase; always merge** to preserve clear and small commit histories.
- Delete stale branches and worktrees promptly as soon as their work is merged.
- Work directly on `main` when designated for root architecture refactorings.
- When using worktrees: one worktree per unit of work, lowercase hyphenated slugs, stage files explicitly.

```powershell
uv run python scripts/worktree.py start fix-sim7600-boundary
uv run python scripts/worktree.py list
```

The helper keeps worktrees beside this repository and carries `.env` only when it exists. Never commit secrets, generated runtime audio, or local credentials.

# Agent Rules <!-- tessl-managed -->

@.tessl/RULES.md follow the [instructions](.tessl/RULES.md)
