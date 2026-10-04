# Running the API/runtime pair

## Local setup

1. From this worktree run `uv sync` and `uv run alembic upgrade head` against your
   intended development database. Do not run migrations during an active call.
2. Configure `apps/api/.env.local` and `apps/runtime/.env.local` using their examples.
   Set identical `VOICE_RUNTIME_CONTROL_TOKEN` and `VOICE_RUNTIME_SERVICE_TOKEN`
   values in both server files. Generate two different high-entropy secrets.
3. Launch API: `uv run uvicorn voice_api.main:app --port 8000 --no-access-log`.
4. Launch runtime in another terminal:
   `uv run uvicorn voice_runner.main:app --port 8001 --workers 1 --no-access-log`.
5. Dashboard uses its API origin and `VITE_RUNTIME_ORIGIN=http://localhost:8001`.
   The API ticket response supplies the direct browser media URL.

Runtime must not run with `--reload` during calls. API reloads do not reload the
runtime, but unavailable API execution leases expire after 30 seconds. Native
runtime opens COM ports for SIM7600; no local Docker audio/COM passthrough is needed.

## Logs and debugging

Set `VOICE_ENABLE_INBOUND_API_LOGS=true` and/or
`VOICE_ENABLE_OUTBOUND_API_LOGS=true` independently in each server's env file.
`VOICE_API_LOG_MAX_BODY_CHARS=8192` bounds previews. Direction-specific
`VOICE_INBOUND_API_LOGS_NO_TRUNCATE` and `VOICE_OUTBOUND_API_LOGS_NO_TRUNCATE` retain
all JSON detail after redaction. Audio/multipart/stream bodies remain metadata.
Use `VOICE_DEBUG_PERF=true` for detailed timing and `VOICE_LOG_LEVEL=INFO`.

Read each terminal's JSON logs and local `data/logs/voice-runtime.jsonl` /
`data/logs/voice-api.jsonl`. Runtime also captures sanitized operational diagnostics into a `runtime_log` artifact,
uploaded directly through the scoped storage interface. Runtime sends live per-run diagnostic batches to
`data/recordings/<run-id>/runtime-diagnostics/` in API storage. Exchange/tool
business evidence remains visible in the existing run inspector. Trace/span IDs
join runtime requests with nested API SDK requests. Error events carry diagnostic
IDs and sanitized stack coordinates; prompts, conversations and secrets are redacted.

Evidence files and `.ack` cursors live in `data/runtime-evidence`. A missing ACK
retains records; replaying committed IDs is safe. Never delete retained files
while diagnosing incomplete delivery. Do not restart or redial uncertain calls.
Python cannot guarantee secure erasure of released secret memory.

## Render setup and acceptance

Deploy the existing API Dockerfile and `Dockerfile.runtime` as separate free web
services. Fill each service's public HTTPS origin and the same two server tokens.
Free services cannot receive private-network traffic: use authenticated public
HTTPS. Set the dashboard public runtime origin and runtime browser-origin allowlist.
Keep Clerk, database, vault, Cloudinary and Supabase administrator credentials only
on the API. Hosted SIM7600 is rejected. Set runtime CPU budget to `0.1`, concurrency
`1`; keep hosted calls disabled in both services until acceptance.

Verify browser audio, chat turns, recording uploads/access,
15-second API delays, 30-second lease expiry, two-service shutdown, and measured
CPU/memory/loop/audio lag before enabling hosted calls. Local multi-session tests
are required before raising concurrency. API status is advisory: runtime admission
is authoritative and immediately rejects busy requests before dialing.

The platform-owner control pings both health endpoints every 10 minutes for up to
72 hours with cross-tab coordination. Keep a signed-in dashboard open. Browser
throttling, Render restarts, cold starts, shared free hours, and ephemeral disk
still limit demo reliability. No production uptime guarantee is implied.

## Local activation

Local activation was authorized on 2026-10-02. Development API routes now dispatch
to the separate runtime. Production now always uses that boundary; hosted execution supports browser, chat and Twilio. Live release testing covers browser/chat; Twilio remains unverified without an account. No services were deployed.
The local database on localhost:55433/voice migrated through 0045.

The primary checkout already owns ports 8000/5173. This testing worktree runs at:

- Dashboard: http://localhost:5174
- API: http://127.0.0.1:8002
- Runtime: http://127.0.0.1:8001

Matching server-only credentials are in ignored `.env.local` files. Start the
native services from this worktree with `./scripts/start-local-services.ps1`.
The launcher leaves occupied ports untouched and writes startup logs beneath
`data/local-service-logs/`. Runtime operational logs are in
`data/logs/voice-runtime.jsonl`; API logs are in `data/logs/voice-api.jsonl`.

84 earlier targeted checks passed, including a 15-second HTTP stall while two
simulated pipeline tasks continued. Local browser binary WebSocket/ticket tests
and active API checks also pass. Actual provider, Twilio, modem audio and Render
acceptance still require operator-run calls. Native startup is verified; Docker
hosting remains unactivated.

For local Twilio testing, expose both API callbacks and runtime media through
canonical public HTTPS origins. API dispatch passes its callback origin once;
the runtime's loopback HTTP control URL must never be used as a Twilio callback.
