---
id: PLAN-0005
title: Dashboard rebuild handoff
status: In progress
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

## Validation before merging

- Dashboard `npm run build` and backend contract validation of minimal agent payload pass.
- Test create/save/publish/clone/activate against a disposable database. Verify invalid flow and missing tool bindings fail without losing unsaved draft edits.
- Test credential write-only behavior, KB upload/rebuild/search, agent tool-version pinning and concurrent draft revisions.
- Check routes by direct URL and back/forward; do not rely on sidebar-only navigation.
- No live dial, external WhatsApp send or secret-bearing log required for dashboard acceptance.
