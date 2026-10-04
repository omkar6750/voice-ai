# Local worktree integration

Target: codex/pipecat-flows-improvements. Local only; main and hosted services
remain unchanged.

## Adapted changes

| Source | Adaptation |
| --- | --- |
| dashboard-read-optimization | Pooled backend Clerk connections without membership caching; release read-only DB checkout before remote authorization; single-query agent summaries; version summary/selected-version reads; bounded runs projections, server filters and keyset pagination; scoped, allowlisted, bounded session cache with delayed writes. |
| api-latency-tracing | Content-free request phases, query count, pool acquisition, response bytes and Server-Timing diagnostics through the current bounded logger; guarded synthetic read benchmark. |
| sim7600-call-diagnostics | Serial command cancellation/timeout safety, bounded modem responses, disconnect recognition, safe modem/pipeline/USB lifecycle diagnostics, background trace writer and conservative cleanup ownership. |
| current editor review | Preserve dirty drafts through background refetch with revision conflict detection; stable fact-field rendering while typing; focused DOM regressions for current pagination/cache/editor. |

Other committed branch work was already included or patch-equivalent. Archived
calendar parsing fixes already exist. Storybook, auth membership caching, old
page layouts, old runtime DB coupling and obsolete diagnostic machinery were
excluded.

## Reads and diagnostics

- Runs: limit=25 (maximum 100), cursor, search, status, channel, agent_version_id,
  created_after and created_before. Cursor identity is bound to tenant and filters.
  No full resolved configuration in list responses. Text tests are excluded.
- Versions: /agents/{id}/versions?view=summary omits configurations;
  /agent-versions/{id} fetches the selected authorized version.
- Set VOICE_DEBUG_PERF=true with VOICE_ENV=dev for content-free read diagnostics.
  Network responses expose Server-Timing and X-Request-ID. api_read_timing logs
  include phase durations, SQL count and response bytes, never SQL or body text.
  Existing inbound/outbound payload switches and redaction remain authoritative.
- SIM7600 dev diagnostics join the existing per-run runtime diagnostic channel;
  the local modem-trace.jsonl uses only fixed fields and enum values. Overflow is
  counted; disk writes do not run on the audio loop. Runtime status retains
  uncertain port reservations even after secret/config references are released.
- Expired assignments become uncertain on an authorized runs read. A confirmed
  terminal batch can reconcile that state. Inspect uncertain transport ownership
  before an operator clears it; nothing automatically retries or redials.

## Local migration and checks

Migration 0047_dashboard_read_index adds a concurrent org/created/id index after
0046_text_tests. Run uv run alembic upgrade head using the testing worktree's
local 55433 DB. Do not run this against main's DB or a hosted service.

Focused verification covers live membership revocation across identical requests,
client closure, metadata-only diagnostic logging, cursor isolation/filters,
summary reads, text-run exclusion, expired lease recovery, late confirmed cleanup,
modem cleanup reservations, cancellation/disconnects, bounded trace overflow,
actual pagination/search/org switches, prompt editor focus and cache filtering.
Run npm run build and the scripts/* test suites named in the handoff.

The synthetic benchmark accepts only a dedicated *_static_reads_test or
*_runtime_split_test database and rolls back its synthetic rows. It measures
local route/projection/serialization and does not model Clerk/provider latency.

Live browser/Twilio/SIM7600 calls and dashboard interaction under audio load still
require operator acceptance. No live external writes or deployment were tested.


## Verified locally, 2026-10-03

- Focused Python unit/runtime checks and Ruff passed.
- Eight isolated PostgreSQL/API contract checks passed; fixtures rolled back.
- Twenty-four dashboard DOM/cache/editor checks passed across the focused suites.
- TypeScript/Vite build passed; generated API declarations include both read APIs.
- One Alembic head; index migration applied to local 55433/voice after isolated verification.
- Idle testing API 8002 and runtime 8001 restarted; both health endpoints passed.
  Loaded OpenAPI confirms selected-version GET and paginated runs response.
  Dashboard 5174 stayed running. Main/hosted services were not changed.
- Synthetic 58-row and 10,000-row workloads returned 25 rows / 8,505 bytes;
  local route-plus-serialization p95 was 6.45 ms and 5.83 ms respectively.
  Synthetic fixtures were rolled back. These are not end-to-end latency figures.

Existing Pipecat deprecation warnings and the DOM harness's occupied HMR port
warning did not fail checks. Live provider/hardware acceptance remains outstanding.
