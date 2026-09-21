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

Run local agent after setting `VOICE_OPENAI_API_KEY`, `VOICE_MODEM_AT_PORT`, and audio device indexes in `.env`:

```powershell
uv run voice-agent --number +15551234567 --modem-port COM7 --openai-api-key $env:VOICE_OPENAI_API_KEY
```

The runtime opens the modem AT port, dials, and sends audio through Pipecat's local audio transport. Select the SIM7600 USB audio device for input and output. Hardware validation remains required because Windows exposes modem audio names and sample rates differently by driver.

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
