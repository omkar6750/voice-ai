# Decision index

| ID | Decision | Status |
| --- | --- | --- |
| [ADR-0001](docs/adr/ADR-0001-runtime-boundaries.md) | Keep API, runtime, and modem edges as explicit local modules | Accepted |
| [ADR-0002](docs/adr/ADR-0002-sqlalchemy-postgres-foundation.md) | Use async SQLAlchemy and Alembic for the first database slice | Accepted |
| [ADR-0003](docs/adr/ADR-0003-provider-adapters.md) | Keep OpenAI and telephony SDK imports behind adapters | Accepted |
| [ADR-0004](docs/adr/ADR-0004-demo-provider-stack.md) | Use Sarvam STT, Groq Llama 3.1 8B Instant, and Cartesia TTS for the demo agent | Accepted |
| [ADR-0005](docs/adr/ADR-0005-voice-test-runtime.md) | Native PCM test lifecycle and available Groq Qwen model; supersedes ADR-0004 | Accepted |
| [ADR-0006](docs/adr/ADR-0006-versioned-configuration.md) | Published configuration, draft concurrency and mutable KB; revision 2 per user request | Accepted |
| [ADR-0007](docs/adr/ADR-0007-exchanges-and-integration-secrets.md) | Run-owned evidence, provider-neutral calls and encrypted integrations; revision 2 per user request | Accepted |
| [ADR-0017](docs/adr/ADR-0017-on-demand-endpoint-probing.md) | On-demand modem probe with five-second monitoring while connected | Accepted |
| [ADR-0020](docs/adr/ADR-0020-node-scoped-transition-tool-schemas.md) | Scope `change_node` destinations to each flow node's transitions | Accepted |
| [ADR-0021](docs/adr/ADR-0021-typed-evidence-and-shared-delivery.md) | Validate evidence events end-to-end, unify final draining, and recover durable spool records safely | Accepted |
| [ADR-0022](docs/adr/ADR-0022-meta-hosted-whatsapp-media.md) | Store WhatsApp template media as connection-scoped Meta IDs; never retain uploaded image bytes locally | Accepted |
| [ADR-0023](docs/adr/ADR-0023-whatsapp-delivery-receipts-in-timeline.md) | Surface correlated WhatsApp webhook delivery receipts as timeline evidence, distinct from send acceptance | Accepted |
| [ADR-0024](docs/adr/ADR-0024-twilio-call-lifecycle.md) | One Twilio close owner, mark/clear playback facts, authenticated callbacks, and fenced dispatch | Accepted |
| [ADR-0025](docs/adr/ADR-0025-callback-role-routing.md) | The model selects a configured callback role; the backend chooses the available person/calendar | Accepted |
| [ADR-0026](docs/adr/ADR-0026-nonblocking-classifier-outcomes.md) | Only `classify_lead` is nonblocking; outcomes are injected before the next caller-turn LLM inference | Accepted |
| [ADR-0027](docs/adr/ADR-0027-remove-unused-wait-settings.md) | Remove inert wait settings; runtime handlers define execution timing | Accepted |
| [ADR-0029 browser transport](docs/adr/ADR-0029-browser-test-websocket-transport.md) | Use Pipecat WebSocket for single browser test calls | Accepted |
| [ADR-0028 Clerk history](docs/adr/ADR-0028-clerk-organizations-workspaces-and-access.md) | Earlier nested tenant proposal | Superseded by Clerk org-only ADR |
| [ADR-0030 Clerk history](docs/adr/ADR-0030-clerk-basic-org-access-for-demo.md) | Earlier basic-org/nested-tenant proposal | Superseded by Clerk org-only ADR |
| [ADR-0031 Clerk org-only](docs/adr/ADR-0031-clerk-organization-is-tenant.md) | Make Clerk Organization the only customer tenant; org-scope all data and record platform admin in DB | Accepted |


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

Text tests share the voice runtime conversation engine: [ADR-0046](docs/adr/ADR-0046-text-tests.md).
Provider adapters: [ADR-0047](docs/adr/ADR-0047-provider-adapters.md) — Isoquant Chat Completions and Gnani SDK WebSocket services.

- [ADR-0048](docs/adr/ADR-0048-fixed-lead-classification.md): fixed classify_lead contract, shared enums and configurable destinations for all 27 combinations.


## 2026-10-03 — Selective local worktree integration

Read optimization, latency diagnostics and modem cleanup changes adapted to the
current separate runtime and editor. No membership authorization cache, Storybook,
main merge or deployment. See ADR-0049 and docs/deployment/WORKTREE-INTEGRATION.md.
Migration 0047_dashboard_read_index follows 0046_text_tests. Live provider/modem
acceptance remains operator-run.

## 2026-10-08 — User-bound MCP capabilities and progressive evidence

[ADR-0053](docs/adr/ADR-0053-mcp-user-access-and-run-debugging.md): serve MCP at
the API boundary with live user membership and reviewed OpenAPI operations;
exclude credential mutation and use an overview-first, explicitly selected,
nonduplicating run evidence contract. Deployment: [MCP access](docs/deployment/MCP-ACCESS.md).
