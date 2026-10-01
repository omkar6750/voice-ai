# Local call performance capture

Enable the content-free timing probes only in development:

```powershell
$env:VOICE_ENV = "dev"
$env:VOICE_DEBUG_PERF = "true"
uv run uvicorn voice_api.main:app --reload --port 8000
```

Restart the API after changing these variables. In production the probes stay
off even if `VOICE_DEBUG_PERF` is set. To switch them off locally, remove
`VOICE_DEBUG_PERF` and restart.

Run four short calls with the same published agent and prompt: browser alone,
browser while opening a dashboard page, SIM7600 alone, and SIM7600 while opening
the same page. Note the time the page was opened. No browser automation is
needed. The API console emits `perf_timing` JSON with epoch milliseconds in
`at_ms`. Each call event includes an opaque `run_id` and transport. API and
loop events can be aligned by `at_ms`.

The probes report:

- `loop/lag`: worst scheduling delay in five seconds and count above 40 ms.
- `api/request`: total request time with method, status and fixed route group.
- `clerk/verify`, `membership/lookup`: authentication and live membership time.
- `db/query`: individual database round trips of at least 20 ms.
- `evidence/batch`: local evidence validation and persistence time.
- `sim_rx/read`, `sim_tx/write`, `sim_tx/flush`: slow serial operations.
- `sim_rx/gap`, `sim_tx/gap`, `browser_audio/gap`: delayed audio frames.
- `capture/frame`: synchronous WAV write taking at least 10 ms.

These timings identify where time is spent; a frame gap alone does not prove
why it happened. Compare its timestamp with loop, API, database and serial
events. Output gaps can also reflect ordinary pauses between utterances.
The log contains no speech, prompts, request paths, credentials or provider
response bodies.
