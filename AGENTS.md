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

## Boundaries

- `apps/api/voice_api` owns HTTP, settings, database sessions, and relational models.
- `packages/voice_runtime/voice_runtime` owns Pipecat pipeline construction and call execution.
- `packages/voice_runtime/voice_runtime/telephony` owns modem protocols and adapters.
- `packages/voice_runtime/voice_runtime/providers` owns provider SDK imports.
- `apps/dashboard` is a thin client. Generate API types from OpenAPI when API surface grows. Do not hand-maintain duplicate DTO contracts.
- Business code depends on local protocols, not vendor SDKs.
- Keep units small. Add an ADR when a settled choice is not obvious from code.

## Pipecat CLI

The project uses Pipecat CLI from `pipecat-ai`.

```powershell
uv run pipecat --help
uv run pipecat --version
uv run pipecat init --list-options
uv run pipecat init . --dry-run
uv run voice-agent --number +15551234567 --modem-port COM7 --openai-api-key $env:VOICE_OPENAI_API_KEY
```

`pipecat init` is useful for checking current scaffold options. Do not scaffold over this repository because its layout and SIM7600 boundary are deliberate. The local development server for this project is FastAPI on port 8000. Vite runs on port 5173. Pipecat's runner is not the public control plane.

For pipeline debugging, use `uv run ruff`, `uv run pytest`, Pipecat log output, and Context Hub API lookups. Real modem and provider checks require hardware and API keys.

## Pipecat Context Hub

Context Hub is installed through the Pipecat CLI and has a local indexed copy of Pipecat docs, examples, and API source. Use it before relying on memory for Pipecat symbols.

```powershell
uv run pipecat context-hub status
uv run pipecat context-hub search-docs "PipelineWorker"
uv run pipecat context-hub search-api "LocalAudioTransport"
uv run pipecat context-hub search-examples "OpenAI voice pipeline"
uv run pipecat context-hub get-code-snippet --symbol "OpenAITTSService"
uv run pipecat context-hub check-deprecation "pipecat.pipeline.task.PipelineTask"
uv run pipecat context-hub refresh
uv run pipecat context-hub serve
```

`status` reports index freshness. `search-*` finds current docs and source. `get-code-snippet` retrieves focused code. `check-deprecation` catches moved APIs. `refresh` updates the local index. `serve` starts the MCP server for an agent client. Context Hub data is stored outside this repository under the user profile. `pipecat context-hub install --client codex` can register the MCP server for a fresh agent setup, then restart the agent.

## Worktrees

One worktree per unit of work. Start from a clean committed branch, use lowercase hyphenated slugs, and stage files explicitly.

```powershell
uv run python scripts/worktree.py start fix-sim7600-boundary
uv run python scripts/worktree.py list
```

The helper keeps worktrees beside this repository and carries `.env` only when it exists. Never commit secrets, generated runtime audio, or local credentials.
