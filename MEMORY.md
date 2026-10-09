# Working state

Phase: RFC-0003 schema review implementation, execution safety and persistence slices.

Cleanup: removed old voice-agent CLI, duplicate config/pipeline/provider factory and
unused modem compatibility exports. Protected demo remains the only live-call entrypoint;
its settings, capture and telephony dependencies remain. DB configuration lives in
contracts/. PLAN-0003 now has an ordered remaining-work checklist and deletion inventory.

Follow-up explicitly authorized demo edit: DemoProviderSettings moved unchanged into
scripts/demo_call.py; now-unused providers package removed. Demo behavior is unchanged.

Completed: typed runtime configs, versioned agents/tools, integration vault/media catalog, mutable
pgvector knowledge, evidence models/spool, compact dashboard, and schema migration.

New: ADR-0006/0007 revision 2 updated in place at user request. Migration 0003 adds
JSONB conversion, publication/binding guards, draft concurrency and Run-owned evidence.
Clone-draft and browser request APIs added; browser requests do not start media transport.

Migration 0004 adds span-linked flow visits, ordered immutable tool results and typed
provider metrics. Finalized evidence now travels through spool, HTTP and PostgreSQL;
timeline includes results and visits. This path is not wired to the live call runner yet.
Credential validation/redaction, environment-backed vault loading and account-scoped
receipt matching are covered. Current full suite: 66 passed, two upstream deprecation warnings.
One old-default-config test was removed with the obsolete implementation.

New: migrations 0005-0010 add endpoint claim fencing, callback attempts, analysis history,
artifact metadata, operational ingestion-token naming and execution ownership guards.
Resolved snapshots include exact tool definitions, KB identities/names, logging/retention,
application/dependency identity and a canonical hash. Claimed snapshots are immutable.
Analysis and artifact APIs, explicit no-redial reconciliation, contact validation and
shared mutable-KB contracts are implemented. Runtime executor uses a call driver and
spool delivery; fake-driver API/database integration is tested. No native pipeline host
has been connected to that executor, so API queueing still does not place real calls.

New: executor streams durable evidence during calls, separately monitors writer health,
and stops execution on permanent ingestion/storage failure. Transient idempotent evidence
requests retry; external calls/actions never do. Cancellation waits for acknowledgement
writes before final drain. Spool creation/close failures now still reach driver cleanup
and incomplete terminal reporting when transport release is confirmed.

Next: native configurable Pipecat host and reviewed action adapters, provider OTel capture,
live tool/flow evidence, classifier/summarizer cadence, recording registration at cleanup,
automatic-callback polling, and ingestion job recovery. Keep legacy Call ownership columns
until compatibility readers migrate; DB guards now prevent disagreement with Run.
Validation: Alembic reports no schema drift; scoped Ruff, OpenAPI/TypeScript generation
and dashboard build pass. See PLAN-0003 for explicit remaining work.
Do not edit `scripts/demo_call.py`.

Validated demo is user-tested reference. Existing DB at 55432 is plain PostgreSQL;
isolated pgvector validation uses port 55433. Provider keys remain local-only.


## 2026-10-02 — Separate runtime implementation checkpoint

Prepared `apps/runtime/voice_runner`, shared pure JSON/compiler/logging contracts,
HTTP dispatch/broker/synchronization and scoped artifact uploads, plus ownership
migrations 0044/0045 and the runtime Docker/Render definition. Runtime packages
have no API/SQLAlchemy imports. Local targeted checks pass with an isolated DB;
no real provider/modem/Render acceptance was run. Active route wiring is pending
explicit activation approval after automatic review rejected changing live call
paths for service-disruption risk. See `docs/deployment/RUNTIME-SPLIT.md` and
`docs/adr/ADR-0044-separate-runtime.md`. Do not deploy or describe the active API
as separated until that wiring and acceptance are complete.


### Local activation authorized

User explicitly authorized running the split locally and prohibited live deployment.
Development routes now use remote dispatch/browser/control; hosted routes remain
unchanged. The testing worktree uses dashboard 5174/API 8002/runtime 8001 to
preserve the primary checkout's 5173/8000 processes. Matching ignored local env
files and a native start-local-services.ps1 launcher are configured; localhost
55433/voice migrated through 0045. Both service health endpoints and authenticated
runtime status respond. Provider/modem call acceptance remains operator-run.

Local text testing: agent versions now have Chat test with direct runtime text WebSocket, single-use tickets, saved tenant conversations/messages/attempts (0046), frozen drafts/published snapshots, interruption and safe continuation, inline errors and inspector. Same Pipecat host skips speech/VAD/capture and speech credential resolution. Live WhatsApp destination is bound to setup. Checkpoint delivery avoids unchanged heartbeat payloads. No production deploy. See docs/deployment/TEXT-TESTS.md and ADR-0046.

Local agent version editor now opens Flow by default. The workspace has handle-based pointer/keyboard node sorting, prompt/task/preview tabs, and expandable right-side settings. Ordering affects only the list; routing and node IDs remain unchanged. Existing global configuration is accessible through the Global prompt tab and Settings menu. Local only.

## 2026-10-02 — Fixed classify_lead contract
Locked three questions, prompts, schemas and JEV endpoint/model; enum routing uses individual labels or all 27 combinations. Existing followup_route mappings preserved. See ADR-0048. Local only.


## 2026-10-03 — Selective local worktree integration

Read optimization, latency diagnostics and modem cleanup changes adapted to the
current separate runtime and editor. No membership authorization cache, Storybook,
main merge or deployment. See ADR-0049 and docs/deployment/WORKTREE-INTEGRATION.md.
Migration 0047_dashboard_read_index follows 0046_text_tests. Live provider/modem
acceptance remains operator-run.

## 2026-10-06 — Referral capture and review

Added the canonical registered `save_referral` business tool, migration
0049_referrals (after contact name parts 0048), scoped review/list/promotion APIs,
and the Referrals dashboard with Contact/Run provenance links. Caller readback
confirmation is separate from operator phone/email verification. Optional phone,
email or name-only referrals are saved independently from Contacts. Only explicit
promotion with a verified international phone creates or links a Contact. No
outreach is triggered. Nullable references survive run/contact cleanup.

Local localhost:55432/voice migrated through 0049; canonical published tool added
to the local Ritu organization's catalog, without changing Ritu's saved prompts,
bindings or published version. Referrals remain backend-only under Supabase RLS;
the migration conditionally grants the server voice_app role and revokes browser
roles. Production has not been migrated/deployed for this feature. See ADR-0051.

## 2026-10-07 — Flat contact prompt variables

Removed name and contact.* from prompt catalogs/runtime state; first_name and
last_name are canonical. Chat snapshots now include these components, matching
browser/modem/Twilio setup. Legacy prompts are translated on copied configuration
and legacy name-only snapshots derive components. Published rows/history remain
immutable. Local drafts updated with revision increments (v11 revision 19).
Migration 0050 repairs missing contact components; full name remains a display
label. Local migration applied, 32 focused tests and dashboard build pass. No
production deployment or live provider acceptance performed. See ADR-0052.

## 2026-10-08 — Secure MCP access and selective run debugging

The control plane now serves stateless Streamable HTTP MCP at /mcp. Dashboard
Settings → MCP access issues environment-bound, hashed, revocable user/org tokens
and copies the token, Codex command or PowerShell setup. Live Clerk membership,
existing member/admin guards and tenant filtering apply on every invocation.
Reviewed OpenAPI tools expose configuration authoring and dashboard operations;
credential writes/deletion, OAuth and platform/runtime control are excluded.
Mutations have durable audit admission and PostgreSQL shared rate limiting.

Run overview includes one full transcript and a compact exchange/node/operation
map, API attempt timings and errors. Selected IDs expose payloads, explicit
deduplicated context, config sections and retained logs. HTTP and modern
WebSocket setup capture never consumes media; coverage states historical,
policy-disabled and uninstrumented gaps. Migration 0051 rehearsed on disposable
PostgreSQL; scoped schema parity and focused MCP/evidence tests pass. Dashboard
build passes. Existing prompt-format, logging-inventory, route-inventory and
run-index parity failures remain unrelated. No production deployment or real
hardware/provider acceptance performed. See ADR-0053 and deployment/MCP-ACCESS.md.
Integrated into the working checkout with backups under .cache/mcp-integration-backup.
Local development PostgreSQL on port 55432 upgraded from 0050 to 0051; 31 focused
tests pass in the integrated checkout. The existing local DB container was started.


## 2026-10-09 — Conversation fact defaults and fallback prompts

Isolated feature worktree adds typed or empty fact defaults, rightmost nonempty
fallback chains, node-entry-only rendering, read-only unsaved previews, Tiptap
fallback insertion and span-linked resolution/provenance evidence. Historical
configurations are not rewritten; no database migration or saved-agent edits.
See ADR-0058 and docs/deployment/PROMPT-FALLBACKS.md. Real provider/modem
acceptance remains operator-run.
