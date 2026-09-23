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
- `packages/voice_runtime/voice_runtime/providers` owns provider SDK imports.
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
contracts/ owns DB-backed agent configuration. The protected demo remains the only
working live-call entrypoint; it uses its own constants, not runtime_endpoints rows.
See PLAN-0003's remaining-work checklist before connecting the configurable runner.

Read RFC-0003, ADR-0006, ADR-0007 and PLAN-0003 before changing config, evidence,
knowledge, or integrations. `scripts/demo_call.py` is tested reference material: do not edit it
without explicit user instruction. Agent/tool drafts use revisions; published versions are immutable.

## Worktrees

One worktree per unit of work. Start from a clean committed branch, use lowercase hyphenated slugs, and stage files explicitly.

```powershell
uv run python scripts/worktree.py start fix-sim7600-boundary
uv run python scripts/worktree.py list
```

The helper keeps worktrees beside this repository and carries `.env` only when it exists. Never commit secrets, generated runtime audio, or local credentials.
