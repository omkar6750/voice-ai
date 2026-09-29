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

## Historical foundation progress (before runtime wiring)

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

First-batch complete suite: **262 passed, 33 skipped, two upstream deprecation
warnings**. Repository Ruff and diff checks pass. Skipped cases require an
isolated PostgreSQL database. No real contacts were called; no hardware, browser
audio, or Twilio carrier playback was verified. No migration or dashboard build
verification has been completed in this worktree yet. Protected demo unchanged.

## Remaining implementation order

1. Idempotent resource cleanup and source-scoped playback observations. Terminal
   nodes now use ordered Pipecat output actions, and graceful shutdown has a
   monotonic deadline. Carrier/browser playback is still not proven by pipeline
   completion; transport-specific acknowledgement remains required.
2. Browser lifecycle follow-up: the supervisor now shares native termination,
   and the modal handles peer closure without stale React state. Verify real audio
   drain and browser rendering; cover abandoned session-creation responses and
   database races. Do not infer physical playback from local pipeline completion.
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
8. Add audit/idempotency/concurrency reconciliation coverage against PostgreSQL,
   not just mocked session tests. Executor artifact-registration failure now
   preserves the primary outcome/error and separately marks evidence incomplete.
9. Generate OpenAPI dashboard contracts, type-check/build, migration/model checks,
   and validate preserved demo/source history. Original checkout remains untouched;
   these commits are not merged or pushed.

Deferred by user: live dashboard WebSocket monitoring and automatic callback
dispatch until the Clerk/production work is ready. Do not silently implement
either as part of these refactors.

## Second reviewed batch, 2026-09-29

Previous goal turn made concrete progress (committed runtime changes), not a
no-progress wait. Inspected the authoritative clean branch before continuing.
One small `gpt-6-luna` worker implemented artifact-outcome separation; parent
reviewed its patch and ran its tests before committing. Terminal lifecycle work
was implemented and reviewed locally. The complete objective remains active.

| Commit | Slice | Evidence |
| --- | --- | --- |
| `e249fa8` | Start flow visit before node response dispatch | Success/failure ordering and transition provenance tests; classifier entry/exit order unchanged |
| `713ed93` | Terminal-node shutdown via ordered Pipecat function action | Installed ActionManager exercised; no close on mere entry; stale/duplicate/disconnected/failed actions guarded; queue failure cannot become success |
| `b7c5d73` | Artifact registration failure separate from call outcome | Completed call stays completed/incomplete; prior pipeline-failure cause/error remain intact |
| `4729a1b` | Bounded graceful shutdown | Default 15-second constructor deadline; monotonic timer unaffected by duplicate requests; immediate/completed calls exempt; timeout causes failed evidence and cancellation |

Second-batch complete suite: **281 passed, 33 skipped, three upstream Pipecat/Python
deprecation warnings**. Ruff and whitespace gates passed before commits. The
additional warning comes from Pipecat's built-in legacy action-handler signature,
not the application's two-argument terminal handler. No vendor source was edited.

Verified against installed Pipecat **1.11.0**, rather than assuming the research
attachment's 1.12.0 semantics: its TTS serialization routes downstream non-system
frames after audio context; base output routes synchronized frames through the
audio queue; Flows invokes FunctionActionFrame at the downstream end. Terminal
action completion is therefore local-output ordering evidence, not proof that a
browser speaker or Twilio carrier rendered the final sample. Playback status
remains unknown until actual source-scoped observations are wired.

Still pending: browser/Twilio finalization and transport acknowledgements,
concurrent/idempotent cleanup, provider usage/pricing persistence and UI, supported
node actions, database/contract/build gates, and physical checks. Main advanced
independently after the branch base; integration must merge and reverify those
changes before completion. Do not use a current-main diff to attribute unrelated
main work to this branch; review this branch's commits from `bcb8d67`.

## Browser and cleanup batch, 2026-09-29

| Commit | Slice | Evidence |
| --- | --- | --- |
| `3471e89` | Browser resource cleanup once, including error paths | Both resource closes attempted; repeated failure remains visible; concurrent and self-finalizer paths tested |
| `bf09392` | Cleanup test import correction | Fixed one import-spacing lint finding; no runtime change |
| `338f627` | Supervisor cancellation joins the conversation task | Child finally finishes before cancellation returns; uploader remains owned by evidence finalization |
| `53c4b36` | Browser and native host share termination facts | Operator stop, disconnect, unknown finish, terminal/agent success and pipeline error distinguished; no provider startup after an already observed stop |
| `e6206d8` | Browser artifact failures are visible and independent | 2xx success; redirects/server errors/timeouts mark incomplete; next file attempted; no retries or raw response persistence |
| `e34a9dd` | Native cleanup serialized and idempotent | Seven tests; tracker/observer failure cannot skip capture; original error/cancellation retained; resource error does not replace completed terminal outcome |
| `aa6b18e` | Dashboard current-peer lifecycle and startup/stop guards | Six Node tests; no stale React state check; actual peer event drives connected; late stop/SDP cannot clear a newer attempt |

Small `gpt-6-luna` workers handled independent scopes. Focused small-model reviews
found no concrete issue in the artifact/native/dashboard final diffs; the parent
reviewed integration and ran all verification before committing. Review corrections
included the successful-close sentinel, preserving repeated cleanup failures,
stop-response attempt identity, and cancelling dialog startup. The dashboard
skill kept existing primitives/styles intact; its file formatting also normalized
existing source. No UI redesign or browser automation was performed.

Latest verification: **316 Python tests passed, 33 database tests skipped**, three
upstream warnings; **six Node tests passed**; repository Ruff and whitespace gates
passed. OpenAPI export, generated dashboard contracts, and dashboard production
build passed in this worktree. Generated contracts remain ignored build artifacts.
Build warns about an existing main JavaScript chunk above 500 kB. No migration
or PostgreSQL concurrency check, physical modem/browser playback, or real Twilio
call was performed. Protected demo is unchanged from `bcb8d67`.

Still open: Twilio supervisor/callback outcomes (they still equate provider
completion with business completion), a single observable hangup owner, mark/clear
acknowledgements, provider usage/pricing persistence and UI, supported node actions,
saved-settings audit, database/race tests, further runtime module extraction, and
integration with updated main. Installed Pipecat's Twilio auto-hangup catches/logs
REST errors instead of propagating them; successful EndFrame alone cannot prove
carrier release. Do not disable auto-hangup until its replacement owns all close
paths and is tested. Browser late session-creation responses are ignored after
attempt cancellation, so abandoned pre-connection run/session expiry still needs
an explicit server-side lifecycle test and cleanup policy. These remain pending,
not silently classified as completed work.
