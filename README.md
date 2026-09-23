# Voice AI

Small voice-agent POC. FastAPI controls state, Pipecat runs the realtime pipeline, and a SIM7600 modem provides the phone call edge on Windows.

## Quick start

```powershell
uv sync
Copy-Item .env.example .env
docker compose up -d db
uv run alembic upgrade head
uv run uvicorn voice_api.main:app --reload --port 8000
```

Run dashboard dev server in a second terminal:

```powershell
cd apps/dashboard
npm install
npm run dev
```

Run Python checks:

```powershell
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Run the validated demo agent after setting `VOICE_SARVAM_API_KEY`, `VOICE_GROQ_API_KEY`, `VOICE_MODEM_AT_PORT`, and `VOICE_MODEM_AUDIO_PORT` in `.env`:

```powershell
uv run python scripts/demo_call.py --number +15551234567
```

The runtime opens COM16 for AT control and COM17 for 16 kHz mono signed 16-bit USB PCM. The validated provider path uses Sarvam STT, Groq Qwen 3.8 27B, and Sarvam TTS. Cartesia remains available as an alternate TTS provider.

## Configuration API status

Configuration publication now requires a body containing the current `revision`.
Tool binding edits also require `revision`; conflicts return HTTP 409. Clone a version
through `/api/agent-versions/{id}/clone` or `/api/tool-versions/{id}/clone` with its revision.
Published versions and bindings are guarded in PostgreSQL.

`POST /api/runs` accepts a browser request with `agent_version_id` and optional `contact_id`.
It persists a queued Run without a telephone Call. Runtime dispatch and browser media
transport remain pending. `/api/calls` likewise persists requests, without dialing yet.

`POST /api/runs/{id}/evidence` accepts versioned finalized evidence batches with safe
replay. Separate flow-visit and tool-result endpoints preserve repeated visits and
delayed result consumption. The timeline joins messages, operation timings, visits and
tool results. Runtime spool delivery is tested end-to-end, but not yet attached to the
live call runner. Start/end records repeat the same operation identity and input metadata;
completion adds final output and optional metrics. Unknown metrics stay null.

For opt-in database tests, point `VOICE_TEST_DATABASE_URL` to an isolated migrated pgvector
database, then run `uv run pytest tests/integration`. Use `VOICE_DATABASE_URL` when applying
`uv run alembic upgrade head`. Never point these checks at production.

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

See [AGENTS.md](AGENTS.md) for workflow, Pipecat CLI, Context Hub, and worktree commands. See [docs/plan/PLAN-0001-initial-foundation.md](docs/plan/PLAN-0001-initial-foundation.md) for RFC extraction and deferred scope.
