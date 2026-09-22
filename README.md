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
