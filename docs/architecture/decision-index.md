# Architecture decision review

Reviewed October 15, 2026 against `42f7b10`. All 46 existing ADRs and 14 RFCs were inventoried; current sources, tests and explicit later decisions control the dispositions below. Three retrospective ADRs were added. No new RFC was created.

Accepted historical records retain their original text. This index supplies current applicability without silently rewriting decisions or claiming proposed work was accepted. Old acceptance counts are dated evidence, not current test results.

## ADR applicability

| Record | Current applicability |
|---|---|
| [ADR-0001](../adr/ADR-0001-runtime-boundaries.md) | Boundary principle remains; separate service ownership is now ADR-0044. |
| [ADR-0002](../adr/ADR-0002-sqlalchemy-postgres-foundation.md) | Current persistence stack; the first-slice schema description is historical. |
| [ADR-0003](../adr/ADR-0003-provider-adapters.md) | Adapter boundary remains; initial provider selection superseded by ADR-0004/0005 and the selectable registry. |
| [ADR-0004](../adr/ADR-0004-demo-provider-stack.md) | Demo provider choice superseded by ADR-0005; not current runtime defaults. |
| [ADR-0005](../adr/ADR-0005-voice-test-runtime.md) | Historical hardware reference; service ownership, speech construction and stop ordering are extended by ADR-0044/0054/0060. |
| [ADR-0006](../adr/ADR-0006-versioned-configuration.md) | Current version/binding invariants; later runtime and credential boundaries extend it. |
| [ADR-0007](../adr/ADR-0007-exchanges-and-integration-secrets.md) | Run/exchange evidence remains. Environment-only provider keys, discarded inbound bodies and no object storage are superseded by later implementation; see current design. |
| [ADR-0008](../adr/ADR-0008-browser-session-version-resolution.md) | Selected-agent version resolution remains. Browser transport/cleanup ownership extended by ADR-0029/0044. |
| [ADR-0009](../adr/ADR-0009-canonical-tool-registry-and-db-cleanup.md) | Registry remains. Development reset and published-edit exceptions are historical operator actions, not normal deletion policy. |
| [ADR-0010](../adr/ADR-0010-tool-context-delivery-evidence.md) | Current delivery/consumption distinction; duplicate notification behavior extended by ADR-0061. |
| [ADR-0011](../adr/ADR-0011-classifier-entry-exit-execution.md) | Entry/exit lifecycle remains; normalized contract and asynchronous callable behavior extended by ADR-0019/0026/0048. |
| [ADR-0012](../adr/ADR-0012-interruption-and-barge-in-evidence.md) | Current interruption evidence; exact remote playback is not established. Gate handling extended by ADR-0061. |
| [ADR-0013](../adr/ADR-0013-runtime-diagnostic-model.md) | Current diagnostic model; development visibility extended by ADR-0054. |
| [ADR-0014](../adr/ADR-0014-tool-and-whatsapp-authoring.md) | Versioned authoring remains; wait controls removed by ADR-0027, media changed by ADR-0022. HTTP authoring does not imply live runtime support. |
| [ADR-0015](../adr/ADR-0015-provider-model-capabilities.md) | Capability ownership remains; fixed old model/provider lists are superseded by the current registry and ADR-0047/0054. |
| [ADR-0016](../adr/ADR-0016-provider-usage-observability.md) | Removed experiment. Account credit/remaining quota is not inferred from local spans. |
| [ADR-0017](../adr/ADR-0017-on-demand-endpoint-probing.md) | On-demand probe remains; runtime ownership/recovery is now ADR-0044/0057/0059. |
| [ADR-0018](../adr/ADR-0018-verbatim-opening-and-context-role-boundary.md) | Opening/semantic role principles remain; global/node composition and provider conversion live in compiler/factory. Legacy persona handling is read compatibility. |
| [ADR-0019](../adr/ADR-0019-classifier-delivery-and-normalized-results.md) | One classifier/context boundary remains; custom criteria replaced by ADR-0048, callable delivery extended by ADR-0026. |
| [ADR-0020](../adr/ADR-0020-node-scoped-transition-tool-schemas.md) | Node-scoped allowed transitions remain; generated go_to_* tools are handled by the current compiler. |
| [ADR-0021](../adr/ADR-0021-typed-evidence-and-shared-delivery.md) | Typed evidence remains; independent lifecycle cleanup extends delivery in ADR-0060. |
| [ADR-0022](../adr/ADR-0022-meta-hosted-whatsapp-media.md) | Current Meta media identity and bounded preview/deletion model. |
| [ADR-0023](../adr/ADR-0023-whatsapp-delivery-receipts-in-timeline.md) | Receipts remain independent of send acceptance; asynchronous delivery extends in ADR-0026. |
| [ADR-0024](../adr/ADR-0024-twilio-call-lifecycle.md) | Twilio lifecycle architecture remains. Separate runtime owns live transport; no fresh live Twilio acceptance. |
| [ADR-0025](../adr/ADR-0025-callback-role-routing.md) | Role/time selection remains; fallback request semantics clarified by ADR-0056. |
| [ADR-0026](../adr/ADR-0026-nonblocking-classifier-outcomes.md) | Current nonblocking classify_lead and caller-turn event delivery; not a generic async setting. |
| [ADR-0027](../adr/ADR-0027-remove-unused-wait-settings.md) | Current removal of unused wait-mode knobs; retain schema normalization for historical data. |
| [ADR-0028](../adr/ADR-0028-clerk-organizations-workspaces-and-access.md) | Fully superseded by ADR-0031; do not recreate nested tenants or custom role hierarchy. |
| [ADR-0029](../adr/ADR-0029-browser-test-websocket-transport.md) | WebSocket transport remains. API-hosted live execution and token exceptions are superseded for production by ADR-0044. |
| [ADR-0030](../adr/ADR-0030-clerk-basic-org-access-for-demo.md) | Fully superseded by ADR-0031; no paid custom Clerk role requirement. |
| [ADR-0031](../adr/ADR-0031-clerk-organization-is-tenant.md) | Current tenant/access model. Temporary org:owner alias still exists; app ownership/platform authority remain separate. |
| [ADR-0044](../adr/ADR-0044-separate-runtime.md) | Current separate runtime. Development in-process paths still exist; production cannot use them. |
| [ADR-0046](../adr/ADR-0046-text-tests.md) | Current text-test architecture; original local-only acceptance statement is historical. |
| [ADR-0047](../adr/ADR-0047-provider-adapters.md) | Current adapter boundaries; model/account availability requires live verification. |
| [ADR-0048](../adr/ADR-0048-fixed-lead-classification.md) | Current fixed three-question classifier and 27-key routing. |
| [ADR-0049](../adr/ADR-0049-selective-worktree-integration.md) | Integration snapshot; preserves current live membership checks and evidence metrics without adding an authorization cache. |
| [ADR-0050](../adr/ADR-0050-whatsapp-template-composer.md) | Composer remains; transcript-only restriction superseded by ADR-0062 structured booking evidence. |
| [ADR-0051](../adr/ADR-0051-referral-capture.md) | Current independent referral review and explicit promotion model. |
| [ADR-0052](../adr/ADR-0052-flat-contact-prompt-variables.md) | Current flat contact variables; copy-based historical normalization remains intentional. |
| [ADR-0053](../adr/ADR-0053-mcp-user-access-and-run-debugging.md) | Current scoped MCP and progressive debugging; instrumented coverage is not complete network capture. |
| [ADR-0054](../adr/ADR-0054-sarvam-realtime-and-development-evidence.md) | Current speech construction/development evidence policy; provider availability remains externally verified. |
| [ADR-0055](../adr/ADR-0055-sim7600-connection-and-release-verification.md) | Current active-call wait and stable release verification; stop order extended by ADR-0060. |
| [ADR-0056](../adr/ADR-0056-terminal-outcomes-and-callback-preferences.md) | Current terminal outcome and unconfirmed callback semantics; failure/release proof still dominate successful entry. |
| [ADR-0057](../adr/ADR-0057-verified-modem-recovery.md) | Current verified recovery; lease expiry or UI state alone cannot release hardware. |
| [ADR-0058](../adr/ADR-0058-conversation-fact-defaults-and-fallbacks.md) | Current fact defaults and node-entry fallback expression resolution. |
| [ADR-0059](../adr/ADR-0059-call-outcomes-and-voicemail.md) | Current release evidence/voicemail decision; October 10 cleanup/isolation portions are separately recorded in ADR-0060/0061. |
| [ADR-0060](../adr/ADR-0060-independent-cleanup-and-operator-stop.md) | Retrospective record of independent cleanup, operator stop fencing and PCM shutdown ordering. |
| [ADR-0061](../adr/ADR-0061-isolated-voicemail-context-and-speech.md) | Retrospective record of classifier context isolation, idempotent delivery and held-speech invalidation. |
| [ADR-0062](../adr/ADR-0062-composer-booking-evidence.md) | Retrospective clarification of the existing structured booking input; partially supersedes ADR-0050. |
| [ADR-0063](../adr/ADR-0063-new-organization-demo.md) | New organizations receive a credential-free starter adaptation and an explicitly redacted historical example with tenant-owned IDs. |
| [ADR-0064](../adr/ADR-0064-storage-and-organization-authorization.md) | Keep server Storage credentials separate from Clerk organization authorization; restricted-role RLS remains a follow-up. |
| [ADR-0065](../adr/ADR-0065-runtime-readiness-and-sarvam-v4.md) | Read-only runtime admission polling, pinned v4 compatibility and opt-in server-only turn timing. |

## RFC applicability

| Record | Status and current reading |
|---|---|
| [RFC-0001](../rfc/RFC-0001-platform-architecture.md) | Historical proposed platform scope. Implemented boundaries are documented by current ADRs; deferred analytics/evaluation goals are not automatically delivered. |
| [RFC-0002](../rfc/RFC-0002-demo-call-voice-runtime-and-optimization.md) | Historical implemented standalone demo. Read with ADR-0005, protected demo_call.py and later configurable runtime decisions. |
| [RFC-0003](../rfc/RFC-0003-configurable-runtime.md) | Accepted foundation. Single-workspace, environment-only model keys, no inbound archive and no remote artifacts are partially superseded. Evidence/version invariants remain. |
| [RFC-0004](../rfc/RFC-0004-dashboard-architecture-and-shell.md) | Proposed dashboard scope. Current React routes and design guide establish implemented pages; proposal is not acceptance evidence. |
| [RFC-0005](../rfc/RFC-0005-agent-authoring-and-flow-editor.md) | Proposed editor scope. Current version contracts, node compiler, task validation and ADR-0058 establish shipped mechanics. |
| [RFC-0006](../rfc/RFC-0006-runs-conversation-timeline-and-trace-waterfall.md) | Proposed timeline/waterfall scope. Current evidence/inspector exist; precise spoken-text alignment and comparative evals remain open. |
| [RFC-0007](../rfc/RFC-0007-contacts-lead-context-and-callbacks.md) | Proposed contacts/callback surface. ADR-0025/0051/0052/0056 describe implemented contact, referral and scheduling behavior. |
| [RFC-0008](../rfc/RFC-0008-knowledge-bases-and-rag-inspection.md) | Proposed knowledge surface. Current API owns mutable corpus ingestion/retrieval; no versioned dataset/corpus guarantee. |
| [RFC-0009](../rfc/RFC-0009-integrations-whatsapp-and-vault.md) | Proposed integrations/vault scope. Current Meta webhook storage/media and scoped vault supersede early environment-only/Fernet-only descriptions. |
| [RFC-0010](../rfc/RFC-0010-tools-catalog-and-provider-schemas.md) | Proposed catalog scope. Registry, published tool bindings and model-stage selection exist; not all authorable providers/tools are accepted for live calls. |
| [RFC-0011](../rfc/RFC-0011-runtime-endpoints-and-diagnostics.md) | Proposed endpoint/reconciliation scope. Separate runtime, strict modem status and verified recovery are implemented; hardware acceptance is independent. |
| [RFC-0012](../rfc/RFC-0012-workspace-analytics-and-quality-metrics.md) | Proposed analytics and quality metrics. Measured per-run spans do not establish a complete analytics/eval product or provider balance API. |
| [RFC-0013](../rfc/RFC-0013-live-call-monitoring.md) | Proposed live monitoring. Do not advertise live listen-only monitoring from transcript polling, saved recordings or the End call control. |
| [RFC-0014](../rfc/RFC-0014-clerk-b2b-onboarding-and-tenant-boundaries.md) | Fully superseded by ADR-0031/PLAN-0040 for tenancy/access; do not implement the old nested workspaces or paid role model. |

## Confirmed replacement relationships

- ADR-0004 replaces the initial provider choice in ADR-0003; ADR-0005 replaces the demo choice in ADR-0004. The adapter boundary survives.
- ADR-0029 replaces browser WebRTC transport details from ADR-0008. ADR-0044 subsequently moves live transport ownership out of the API.
- ADR-0031 explicitly supersedes ADR-0028, ADR-0030 and the tenancy proposal in RFC-0014.
- ADR-0027 removes the wait-mode controls described in older tool-authoring records.
- ADR-0048 replaces custom classifier questions/labels with the fixed classification contract.
- ADR-0052 replaces old name/contact.* prompt authoring with flat variables while preserving historical reads.
- ADR-0054 replaces legacy Sarvam per-frame STT execution; current provider support is defined in code.
- ADR-0060/0061 formalize already implemented October 10 lifecycle/isolation details from ADR-0059. They do not replace its release-attribution rule.
- ADR-0062 supersedes only the transcript-as-sole-user-message restriction in ADR-0050.

## Review limits

All source records were read into the audit inventory and their decisions/references inspected. This is not a claim that every historic requirement was accepted or every live service was checked. Current environment values, production data, external model access and hardware remain outside a documentation audit. Superseded body text is retained to preserve the decision trail.
