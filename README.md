# Voice AI

Small voice-agent POC. FastAPI controls state, Pipecat runs the realtime pipeline, and a SIM7600 modem provides the phone call edge on Windows.

## Quick start

```powershell
uv sync
if (-not (Test-Path apps/api/.env)) { Copy-Item apps/api/.env.example apps/api/.env }
docker compose --env-file apps/api/.env up -d db
uv run alembic upgrade head
uv run uvicorn voice_api.main:app --reload --port 8000
```

Run dashboard dev server in a second terminal:

```powershell
cd apps/dashboard
npm install
npm run dev
```

The dashboard currently builds Runs and a read-only pinned agent-version reference.
Other menu routes show explicit placeholders. Runs needs the current API with
`GET /api/v1/runs`, its timeline and artifact routes, plus a migrated PostgreSQL
database. If an older API already owns port 8000, start the current API on another
port and set the dashboard's `VITE_API_ORIGIN` in `apps/dashboard/.env.local`:

```powershell
$env:VITE_API_ORIGIN = "http://127.0.0.1:8001"
npm run dev
```

The dashboard stores the operator token only in memory. A reload requires reconnecting.

Run Python checks:

```powershell
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Run the validated demo agent after setting `VOICE_SARVAM_API_KEY` and `VOICE_GROQ_API_KEY` in `apps/api/.env`:

```powershell
uv run python scripts/demo_call.py --number +15551234567
```

The runtime opens COM16 for AT control and COM17 for 16 kHz mono signed 16-bit USB PCM. The validated provider path uses Sarvam STT, Groq Qwen 3.8 27B, and Sarvam TTS. Cartesia remains available as an alternate TTS provider.

Demo ports, models and prompts are constants in the protected script, not environment
overrides. DB-backed configuration lives in agent versions and runtime endpoints.
The obsolete voice-agent command and duplicate default-config/pipeline were removed.

## Configuration API status

Configuration publication now requires a body containing the current `revision`.
Tool binding edits also require `revision`; conflicts return HTTP 409. Clone a version
through `/api/agent-versions/{id}/clone` or `/api/tool-versions/{id}/clone` with its revision.
Published versions and bindings are guarded in PostgreSQL.

`POST /api/runs` accepts a browser request with `agent_version_id` and optional `contact_id`.
It persists a queued Run without a telephone Call. Runtime dispatch and browser media
transport remain pending. `/api/calls` likewise persists requests, without dialing yet.

Execution now supports endpoint registration, fenced claim/lease renewal, safe callback
launch and explicit restart reconciliation. The executor is tested with fake call drivers;
its configurable native Pipecat host is not connected yet. Do not expect queued API calls
to dial automatically. `demo_call.py` remains the working hardware reference.

Run analysis and artifact APIs preserve finalized evidence and expire registered call files.
Knowledge ingestion settings are separate from retrieval controls; source rebuild is explicit
after changing chunk settings. Existing chunks remain usable until replacement succeeds.

`POST /api/runs/{id}/evidence` accepts versioned finalized evidence batches with safe
replay. Separate flow-visit and tool-result endpoints preserve repeated visits and
delayed result consumption. The timeline joins messages, operation timings, visits and
tool results. Runtime spool delivery is tested end-to-end, but not yet attached to the
native Pipecat pipeline. The configurable executor already uploads evidence during calls
when driven by a test driver. Start/end records repeat the same operation identity and input metadata;
completion adds final output and optional metrics. Unknown metrics stay null.

For opt-in database tests, point `VOICE_TEST_DATABASE_URL` to an isolated migrated pgvector
database, then run `uv run pytest tests/integration`. Use `VOICE_DATABASE_URL` when applying
`uv run alembic upgrade head`. Never point these checks at production.

Check model/migration parity with `uv run alembic check`. Generate frontend contracts with
`uv run python scripts/export_openapi.py`, then `npm run generate` inside `apps/dashboard`.

## Project shape

```text
apps/api/                 FastAPI control plane
apps/dashboard/           Minimal React/Vite shell
packages/voice_runtime/   Pipecat, provider, and telephony code
migrations/               Alembic migrations
scripts/                  Development utilities
tests/                    Unit and API tests
docs/                     RFC, ADR, plan, and working state
data/recordings/          Local call recordings, ignored by Git
```

See [AGENTS.md](AGENTS.md) for workflow, Pipecat CLI, Context Hub, and worktree commands.
See [PLAN-0003](docs/plan/PLAN-0003-configurable-runtime.md#remaining-work-after-cleanup)
for current remaining work. PLAN-0001 is historical foundation context.
