# Runtime architecture implementation ledger

Branch: `codex/runtime-architecture-fixes`, based on main `bcb8d67`.

The two supplied research attachments are suggestions. Verify SDK semantics
against the locked dependency source and official documentation before using
them. Preserve published snapshots and the protected demo.

## Required work and completion evidence

- [ ] Typed termination cause, graceful/immediate mode, playback and cleanup
  facts shared across SIM7600, browser, and Twilio; race/idempotency tests.
- [ ] Resolve end-call result before termination; terminal response completion;
  bounded draining, immediate external disconnect, visible timeout evidence.
- [ ] One Twilio hangup owner, mark/clear playback tracking, provider status
  confirmation, and callback ordering/deduplication tests.
- [ ] Correct SIM7600 hangup/PCM cleanup and confirmed release tests.
- [ ] Typed node lifecycle actions for tools without LLM input; publish/runtime
  capability validation; classifier cadence remains separately evidenced.
- [ ] Auditable reconciliation preserves historical outcome/evidence and proves
  worker stop plus transport release; concurrency tests.
- [ ] Provider-neutral operation/attempt usage accounting, classifier and
  summarizer measurement, nullable provenance/coverage, retries/interruption.
- [ ] Versioned pricing and immutable cost evidence, cached/reasoning units,
  separate currencies, missing/ambiguous pricing; aggregation API and UI.
- [ ] Provider/runtime capability audit and accurate settings UI; no inactive
  controls that pretend to apply. Automatic language switching/Krisp deferred.
- [ ] Native runtime modules concentrate flow compilation, provider construction,
  actions, lifecycle, and evidence with small testable interfaces.
- [x] Callback base URL uses deployment settings; non-success HTTP responses
  fail before JSON decoding, errors are sanitized, writes are not retried.
- [ ] Fix known malformed tests/lint and verify contract generation/build.
- [ ] Full Python tests/lint, OpenAPI generation, dashboard types/build, migration
  checks where DB is available; record unavailable physical verification.

Live dashboard WebSocket monitoring and automatic callback dispatch remain
deferred until Clerk/production work as previously requested. Historical data
cleanup is not repeated in this isolated checkout.

## Progress

- Read both research attachments completely and inspected current main.
- Created an isolated managed worktree and branch; installing locked dependencies.

- Locked dependencies installed independently in this worktree: Pipecat 1.11.0.
  Context Hub reports indexed Pipecat 1.11.0 (index eight days old). Inspected
  installed Flows actions/manager and Twilio serializer source: serializer
  auto-hangup is real; tool callbacks precede post-result work; Flows deferred
  post-actions use BotStoppedSpeaking, not TTSStopped.
- Main already contains snapshot injection, configurable callback API base URL,
  corrected WhatsApp test context managers, and clean baseline Ruff output.
- Added isolated `execution/termination.py` and 11 passing behavioral tests for
  cause/mode/cleanup separation, idempotency, interruption, failure during
  goodbye, and unknown outcomes. This module is not wired into the runtime yet.
- Historical blocker: automatic approval review rejected runtime wiring twice because it treated the
  earlier planning-only request as active. The actual active goal was inspected
  and explicitly authorizes implementation; the reviewer still rejected the
  second attempt. No rejected runtime edits were applied. Further live runtime
  changes required resolving that approval restriction. The user explicitly
  reauthorized implementation on 2026-09-28; implementation resumed successfully.
- Full isolated suite passed after fixing two PKCE tests that incorrectly
  depended on local Google credentials. They now use fake settings and construct
  authorization URLs without network calls. 33 database integration cases skip
  unless an isolated `VOICE_TEST_DATABASE_URL` is configured. Fixed the Twilio
  session mock to match SQLAlchemy's synchronous `add` method as well.
- Ruff passes. Physical SIM7600, browser audio, and Twilio calls have not been
  exercised; runtime wiring and the other ledger requirements remain pending.
- Added independent `execution/accounting.py` with 27 passing behavior tests.
  It references existing operation IDs, tracks attempts separately, preserves
  missing versus zero, exposes estimate/partial coverage, uses Decimal cost
  arithmetic, rejects duplicate attempts and overlapping prices, matches tier
  and effective date explicitly, pins immutable price evidence, and separates
  currency totals. Explicit adapter-produced billable dimensions avoid cached
  and reasoning double charging. No provider prices were invented or seeded.
- Accounting is not yet connected to provider collection, evidence ingestion,
  migrations, APIs, or dashboard. Those requirements remain open; the module
  and its tests are implementation progress, not completion of token accounting.
- Combined verification after this progress: 217 passed, 33 skipped, two
  upstream deprecation warnings; repository Ruff and diff whitespace checks
  pass. Skipped cases require an isolated PostgreSQL test database.

Nothing above is complete solely because this ledger exists.

## Reviewed small commits, 2026-09-29

The user requested small changes and reviews before committing. The subagent
tool does not offer `gpt-5.6-luna`; five implementation workers used the available
small `gpt-6-luna`. The parent performed focused pre-commit reviews, as permitted
by the user's fallback. No large-model review subagents were used. Workers did
not commit, and all changes are confined to this isolated worktree.

| Commit | Slice | Review and verification |
| --- | --- | --- |
| `8f3b943` | Deterministic calendar settings and SQLAlchemy session mocks | Test-only; 12 focused cases pass |
| `8283d40` | Termination intent, observed cause, playback and cleanup model | Goodbye interruption corrected before commit; foundation remains transport-neutral |
| `7ab49ad` | Independent provider-neutral accounting and immutable cost calculations | 27 cases; missing versus zero, retries, currency separation and ambiguous prices |
| `b56c42a` | Callback HTTP failures | Preserve success JSON/auth/payload/20-second timeout; reject redirects and HTTP errors; no retry on timeouts or malformed JSON |
| `4626942` | Reconciliation history preservation | Retain old audit-field locations; five safety/history cases; no relaxed locks or redial |
| `408ee31` | End-call tool result precedes graceful shutdown | Actual installed Flows wrapper exercised; ordinary tool inference unchanged; duplicate end requests queue one frame |
| `e57b57d` | Speech-provider construction tests | Parent fixed two test-fixture errors; no production behavior changed |
| `c91ade3` | Speech construction module extraction | AST exactly matches original function; native import path retained; 13 focused cases |
| `2c2eaa4` | Truthful native termination/evidence | Pipeline failure after end intent remains failure; unknown and cancellation cannot become completed evidence; first external cause survives cleanup |
| `daa59ed` | Flow-manager module extraction | Class AST exactly matches original; native import path retained; complete suite passes |
| `d13412b` | Executor reports typed native outcome | Dropped/incomplete calls report failed with specific cause; endpoint release still fenced; 12 cases including malformed termination and legacy driver behavior |

Review corrections were made before committing: reject redirect responses; keep
reconciliation audit keys compatible; require pipeline completion rather than
close intent for success; retain first immediate external cause during cleanup;
preserve unknown pipeline completion; ensure malformed termination sets failed.

Latest complete suite: **262 passed, 33 skipped, two upstream deprecation
warnings**. Repository Ruff and diff checks pass. Skipped cases require an
isolated PostgreSQL database. No real contacts were called; no hardware, browser
audio, or Twilio carrier playback was verified. No migration or dashboard build
verification has been completed in this worktree yet. Protected demo unchanged.

## Remaining implementation order

1. Terminal-node close after response playback, bounded graceful draining,
   idempotent resource cleanup, and playback observations. Current end-call
   ordering is fixed, but carrier playback is not proven by pipeline completion.
2. Browser lifecycle: distinguish explicit operator stop, peer disconnect,
   successful terminal completion and pipeline failure. The browser supervisor
   still uses its existing final-status rules; native evidence fixes alone do
   not fix that supervisor.
3. Twilio lifecycle: one hangup owner, mark/clear acknowledgements, bounded drain,
   confirmed REST completion, callback ordering and duplicate-event rules. No
   assumptions about carrier playback or caller disinterest from disconnect.
4. SIM7600 release and cancellation races: preserve confirmed-idle fencing,
   verify hangup/USB cleanup and failure paths; physical firmware check remains
   necessary before claiming full hardware correctness.
5. Pricing/usage collection: connect the independent accounting module to
   existing operation spans, explicit retry attempts, classifier/summarizer
   usage and provider normalizers. Add durable pricing/cost evidence, nullable
   coverage, aggregation contracts and dashboard presentation. No price registry
   is seeded and no current cost total includes this module yet.
6. Supported typed entry/exit actions and publication checks. The generic saved
   action/background fields still remain unsupported; classifier cadence is a
   separate working implementation and was preserved by the extraction.
7. Continue extracting actual action implementations and provider construction
   where this improves locality, not by adding pass-through wrappers. Add
   debugging instructions and capability tests for remaining saved settings.
8. Evidence/artifact failures must not overwrite a successfully completed call;
   the executor's existing artifact-registration failure policy still needs its
   own reviewed slice. Add audit/idempotency/concurrency reconciliation coverage
   against PostgreSQL, not just mocked session tests.
9. Generate OpenAPI dashboard contracts, type-check/build, migration/model checks,
   and validate preserved demo/source history. Original checkout remains untouched;
   these commits are not merged or pushed.

Deferred by user: live dashboard WebSocket monitoring and automatic callback
dispatch until the Clerk/production work is ready. Do not silently implement
either as part of these refactors.
