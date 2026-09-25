---
id: PLAN-0005
title: Dashboard rebuild handoff
status: Complete
baseline: 2b50710
date: 2026-09-25
related: [RFC-0004, RFC-0005, RFC-0006, RFC-0007, RFC-0008, RFC-0009, RFC-0010, RFC-0011]
---

# Dashboard rebuild handoff

## Rules

- Keep Runs timeline, transcript and audio intact until other pages work. Revisit trace-order bugs last.
- Use exact API response wrappers. Do not assume lists are bare arrays.
- Load a complete agent version and patch that same object. Never reconstruct configuration from form fields.
- Read model choices from `GET /api/v1/providers`, exact tool versions from `GET /api/v1/tools/{id}/versions`, and current settings from saved config. Backend does not yet advertise credential readiness, voice choices, or per-model capabilities. Show those as read-only, not guessed selectors.
- Use shadcn primitives, existing semantic tokens, Tailwind utilities, and small page modules. Page scroll is okay; avoid nested scrolling forms.
- Preserve operator token in memory. Do not log or persist it.

## Built in this branch

- Narrow, collapsible shadcn navigation and reload-safe React Router paths.
- Agents list, minimal draft creation, version history, clone/publish/activate, modular editor for prompts, flow, model settings, audio, context readout, tools, knowledge and logging.
- Agent edits preserve unexposed config fields. Save uses revision and retains unsaved edits on conflict.
- Prompt tool-call syntax highlights bound names and warns on unbound function-style names. Flow node controls only offer existing binding keys.
- Contacts list/create, KB list/create/source upload/search/ingestion settings, tool/version inspection, WhatsApp connection/credential/media/template surfaces, workspace settings.
- Honest pending pages for callbacks and endpoints, because required list APIs do not exist.
- Runs code unchanged from baseline.

## Required backend APIs before adding more controls

1. `GET /api/v1/runtime-endpoints`: return `{ endpoints: [{ id, name, config: { at_port, audio_port, baudrate, ... }, active_run_id, status: { checked_at, alive, sim_ready, can_make_call, radio_access, rssi, usb_audio_active, last_error } }] }`. Current POST registration and recover routes cannot populate a list or health view. Status must be live, timestamped and separate from saved config. Add PATCH only if endpoint editing is intended; use revision protection.
2. `GET /api/v1/callbacks`: return `{ callbacks: [{ id, contact_id, agent_version_id, due_at, timezone, status, automatic_attempts, call_id, last_error }] }`. Support status/due filters and pagination when needed. Existing POST/launch routes cannot populate queue view. Automatic launch worker state must be queryable before UI claims automation is running.
3. `PATCH /api/v1/integrations/{id}`: accept expected revision plus `{ label, enabled, config }`, return sanitized connection summary. Existing POST always starts disabled, with no way to enable or update. Never return credential values. Validate WhatsApp account IDs and API version.
4. `GET /api/v1/providers` expansion: for each configured slot/model return `available` (credential/setup check only), supported editable fields with bounds/defaults, supported languages where known, and TTS voice IDs/names from provider API if available. Distinguish backend-configured from runtime-verified. No secret values. Until then TTS voice/model/provider stay read-only in UI.
5. `GET /api/v1/tools/handlers`: return reviewed registered handler names and parameter schemas, plus whether runtime supports each handler. For HTTP tools, expose destination allowlist policy and validation response. Only then add safe tool creation/edit forms. Current tool list/versions do not define allowed handler options.
6. `PATCH /api/v1/contacts/{id}` and contact detail/facts/history read routes. Current GET is list-only and POST is create-only. Add conflict protection and validate E.164/IANA timezone. Do not render fake lead facts.
7. Agent configuration capability response: identify which saved fields actually affect live calls. `GET /api/v1/config-schema` gives shape and validation but not runtime wiring or model-specific applicability. Expose applied/pending/read-only status per field (and reason) before enabling remaining cadence/language/TTS controls.
8. `GET /api/v1/agents/{id}/versions/{versionId}` would avoid downloading every full version to edit one. Return `{ id, agent_id, version, revision, status, config, note }`. Existing list works for now. Add a preflight validation route only if publication errors cannot be presented clearly from existing PATCH/publish responses.

## Remaining frontend work

- Add a contact detail route after API 6; include facts and related runs, not fabricated metrics.
- Add callback queue and endpoint status/config screens after APIs 1 and 2. Call launch must select existing contact, published agent version and claimed endpoint; never send raw `to_number`/`agent_id` to `POST /calls`.
- Add safe tool draft and WhatsApp account edit forms after APIs 3 and 5. Media import by existing ID is optional; upload/catalog already work.
- Add TTS voice/language and cadence controls only after APIs 4 and 7 prove available options and runtime application. Currently stored values remain visible.
- Replace local narrow TypeScript response shapes with generated OpenAPI types once endpoint responses are formalized. `GET /config-schema` is available for validation; no invented frontend registry.
- Add in-app unsaved-navigation guard, prompt token insertion/autocomplete, and explicit draft conflict diff. Current browser unload guard and inline warnings are the first slice.
- Revisit Runs last: globally consistent waterfall time axis, chronological message/tool ordering, flow-visit linkage, honest provider-operation count. Keep recording/audio support.

## 2026-09-25 operator workflow expansion

Implement these after checking existing API and runtime contracts. Do not imply that a saved setting affects a live call until the runner consumes it. Keep `scripts/demo_call.py` unchanged and preserve the Runs page.

1. **Quick dial and queue.** Add a small Quick dial action at the right of the breadcrumb bar. Select an existing contact, a published agent version, and an available runtime endpoint. Show only call options the backend actually accepts, including logging override. Submit `POST /api/v1/calls` with `dispatch: true` by default. Offer an explicit Queue instead action with `dispatch: false`. Queued requests are durable records, not scheduled callbacks; show their status and let the operator dispatch a queued call through `POST /api/v1/calls/{id}/dispatch`. Surface claim/conflict errors and never redial an uncertain request. Add a safe endpoint listing API if absent.
2. **WhatsApp template tools.** One action connection may serve multiple approved templates. Fetch templates for that connection, bind each selected template to a separately named, versioned tool whose name includes a stable sanitized template identifier. Its description, parameters, connection and template/language must be clear to the agent and pinned at publish time. Capture exact send parameters, selected media and provider message ID in the invocation. Avoid a separate message archive. Add only the tool/connection APIs needed by the editor.
3. **Direct messages.** Define a separate direct-message action with an enforced 24-hour customer-service window. Track only transient latest-inbound timestamp per sender/account, never archive inbound bodies; unknown eligibility after restart fails closed and directs the operator/agent to an approved template. Verify Meta's current window and send rules before implementation. Keep webhook receipt matching account-scoped.
4. **Models catalog.** Decision from operator: use authenticated live model discovery with aggressive caching. Groq and Gemini both document model-list APIs. Only enable a choice when the installed Pipecat adapter and model capabilities support the live text/tool pipeline; display discovered but unsupported models as read-only, never invent entries. Cache errors must not silently masquerade as an empty catalog.
5. **Classifier and summarizer.** Wire classifier configuration to flow-node entry/exit and expose keyword and multiple rule triggers, cadence/cooldown, model/output settings, and enablement in small editor sections. Apply equivalent multi-rule controls to summarization. Define rule composition and trigger evaluation explicitly in typed backend contracts and runtime before labeling UI controls active. Preserve existing tested defaults and show unsupported features as read-only/pending.

## Detailed Status Matrix (Done vs In-Progress vs Remaining)

### 1. Backend Core & APIs
- [x] **Database & Migrations**: Asyncpg + pgvector PostgreSQL, migrations 0001-0010 complete. Fenced execution, draft revisions, run-owned evidence, immutable tool snapshots.
- [x] **Agent Authoring & Versioning**: `GET/POST /agents`, `GET/PATCH /agent-versions/{id}`, `POST .../clone`, `POST .../publish`, `POST .../activate`. Revision concurrency guards active.
- [x] **Knowledge Base**: `GET/POST /knowledge-bases`, file upload, chunking, pgvector search, reindex routes.
- [x] **Integrations Foundation**: `GET/POST /integrations`, `PUT .../secrets/{name}` (Fernet encrypted), `POST .../rotate-secrets`, media import/upload, template listing, WhatsApp webhook signature verification & account-scoped receipt tracking.
- [x] **Call Execution Engine**: `POST /calls` with `dispatch: true|false`, `POST /calls/{id}/dispatch`, `GET /calls`, `GET /calls/{id}`, `POST /runs/{id}/claim`, `POST /runs/{id}/progress`.
- [x] **Dial Options Endpoint**: `GET /dial-options` returns published agent versions and runtime endpoints with occupancy status.
- [x] **Runtime Endpoints List (API 1)**: `GET /api/v1/runtime-endpoints` with live status (`alive`, `sim_ready`, `can_make_call`, `radio_access`, `rssi`, `usb_audio_active`, `last_error`).
- [x] **Callbacks Queue Listing (API 2)**: `GET /api/v1/callbacks` with status/due filters, pagination, and automatic attempts state.
- [x] **Integration Update (API 3)**: `PATCH /api/v1/integrations/{id}` with expected revision for label, enabled toggle, and validated config.
- [x] **Providers Expansion (API 4)**: Credential readiness indicators, bounds/defaults, supported languages, and TTS voice ID catalog integration.
- [x] **Tool Handlers Catalog (API 5)**: `GET /api/v1/tools/handlers` exposing registered handlers (`change_node`, `end_call`, `send_whatsapp_template`, `send_whatsapp_message`, etc.), parameter schemas, and HTTP allowlist policies.
- [x] **Contacts Detail & Edit (API 6)**: `GET/PATCH /api/v1/contacts/{id}`, facts, call history with E.164 and IANA timezone validation.
- [x] **Config Schema Capabilities (API 7)**: Endpoint exposing which fields are live-applied vs pending/read-only in the Pipecat runner.

### 2. Frontend Dashboard Surfaces
- [x] **App Shell & Layout**: Collapsible shadcn sidebar, breadcrumb trail, operator token in browser memory, zero CSS modules or handwritten style rules.
- [x] **Agents List & Editor**: Version history, clone, publish, activate, tabs for Prompts, Flow, Models, Audio, Context, Tools, Knowledge, Logging. Tool call highlighter and binding checks.
- [x] **Quick Dial Sheet**: Header quick action for launching calls (`dispatch: true`) or queuing (`dispatch: false`), showing occupied endpoints and listing queued calls for one-click dispatch.
- [x] **Models Panel (First Slice)**: Provider switch (Groq / Gemini), model dropdown from live discovery, temperature, max tokens, top-p, and read-only reasoning effort.
- [x] **Callbacks Page**: Replaces `PendingPage` with scheduled callbacks table, due-window indicators, and manual launch trigger.
- [x] **Endpoints Page**: Replaces `PendingPage` with endpoint cards/table showing hardware port assignments (COM16/COM17), live signal metrics (RSSI, radio access), and lease recovery.
- [x] **Contact Detail Page**: Dedicated route `/contacts/:id` showing contact profile, facts, past runs, and quick callback scheduling.
- [x] **WhatsApp Multi-Template Tool Generator**: UI on Integrations / Tools page to select an approved template and generate a pinned, versioned tool.
- [x] **Direct Message Tool & 24h Window Indicator**: Visual status of the 24-hour customer service window for a contact and direct message tool configuration.
- [x] **Classifier & Summarizer Editor**: Dedicated panels in Agent Editor with keyword triggers, multiple rule triggers, confidence thresholds, and node entry/exit bindings.

## Technical Specifications for Operator Expansions

### A. WhatsApp Multi-Template Tools Architecture
1. **Template Discovery**: `GET /integrations/{id}/templates` returns approved templates from Meta Graph API.
2. **Stable Tool Naming**: Tools generated from templates follow the sanitized pattern `whatsapp_template_<sanitized_template_name>` (e.g., `whatsapp_template_dialtone_followup`).
3. **Parameter Generation**: Inspects template components (header parameters like media ID, body positional parameters `{{1}}`, `{{2}}`, etc.) and produces JSON Schema properties for the tool.
4. **Execution & Evidence**: When the LLM invokes `whatsapp_template_<name>`, the runtime loads the connection's encrypted token, formats Meta payload with pinned template name & language code, executes `POST /messages`, and records `ToolInvocation` with provider message ID and receipt correlation.

### B. Direct Messaging & 24-Hour Customer-Service Window
1. **Inbound Window Tracking**: `InboundWindow` in `whatsapp_service.py` records transient `(connection_id, recipient)` timestamps upon webhook receipt. Memory-only; restarts deliberately fail closed.
2. **Window Tool Handler**: Expose `check_whatsapp_window(to: str)` tool to allow agent to query if 24h window is open.
3. **Direct Message Handler**: Expose `send_whatsapp_message(to: str, text: str)` tool. Handler checks `allows_text(connection_id, recipient)`. If closed or unknown, rejects with explicit guidance to use an approved template tool.
4. **Account Scoping**: Webhook verification and receipt tracking are strictly partitioned by `waba_id` and `phone_number_id`.

### C. Live Models Discovery & Pipecat Provider Compatibility
1. **Groq Discovery**:
   - Upstream API: `GET https://api.groq.com/openai/v1/models` (`Bearer <GROQ_API_KEY>`).
   - SDK: `groq` package (`groq.Client().models.list()`).
   - Filter criteria: Active models matching vetted chat completion IDs (`llama-3.1-8b-instant`, `llama-3.3-70b-versatile`, `qwen/qwen3.8-27b`, etc.). Excludes transcription-only models (`whisper-*`).
2. **Google Gemini Discovery**:
   - Upstream API: `GET https://generativelanguage.googleapis.com/v1beta/models?key=<GEMINI_API_KEY>`.
   - SDK: `google-genai` / `google-generativeai`.
   - Filter criteria: Model names starting with `models/gemini-`, supporting `generateContent`, excluding `-image`, `-tts`, `-live`, `-audio`.
   - Pipecat Runtime Compatibility: Pipecat `GoogleLLMService` requires `pipecat-ai[google]` extra in `pyproject.toml` (which installs `google-api-core` and `google-generativeai`).
3. **Caching & Resilience**:
   - Process-local in-memory cache keyed by SHA-256 hash of API key with 6-hour TTL (`TTL_SECONDS = 21600`).
   - On upstream network/API failure, serve stale cache if available, or return status `"unavailable"` without leaking raw error payloads or credentials.

### D. Classifier & Summarizer Node Wiring and Multi-Rule Triggers
1. **Classifier Triggers**:
   - **Node Entry/Exit**: Evaluated on transition into or out of specified `FlowNodeConfig` nodes (`node_exits`).
   - **Keyword-Based Triggers**: Exact regex/string match against user turns or full transcripts.
   - **Multi-Rule / Signal Triggers**: Answer signals (`answer_signals`), topic signals (`topic_signals`), and confidence thresholds (`confidence_threshold >= 0.8`).
   - **Consecutive Verdicts**: Requires `consecutive_verdicts` matches before declaring final lead classification.
2. **Summarizer Triggers**:
   - Compaction threshold ratio (`compaction_threshold = 0.7`), hard ceiling (`0.9`), and target ratio (`0.4`).
   - Unsummarized exchange counter (`unsummarized_messages`, `unsummarized_exchanges`).
   - Preserves opening messages (`preserve_opening_messages = 2`) and recent messages (`preserve_recent_messages = 6`).
3. **UI Controls**:
   - Small, dense editor panels within Agent Editor tabs.
   - Clear indicators showing whether classifier/summarizer logic is actively executed by the runtime or held in config snapshot.

## Validation before merging

- Dashboard `npm run build` and backend contract validation of minimal agent payload pass.
- Test create/save/publish/clone/activate against a disposable database. Verify invalid flow and missing tool bindings fail without losing unsaved draft edits.
- Test credential write-only behavior, KB upload/rebuild/search, agent tool-version pinning and concurrent draft revisions.
- Check routes by direct URL and back/forward; do not rely on sidebar-only navigation.
- No live dial, external WhatsApp send or secret-bearing log required for dashboard acceptance.
