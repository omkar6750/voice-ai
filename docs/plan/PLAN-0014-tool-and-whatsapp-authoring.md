# PLAN-0014 · Tool and WhatsApp authoring

Status: completed

## Existing facts

- Tool edit APIs exist for drafts, but the dashboard exposes mostly clone/publish.
- WhatsApp media upload and template generation are partially implemented.
- Registered tools currently show HTTP-only fields as “Not applicable”.

## Scope

- Add a typed version-aware tool editor.
- Separate registered-handler and HTTP tool forms.
- Add a reusable WhatsApp media catalog and template binding workflow.

## Contracts

- Add typed tool configuration/editor responses.
- Add media display name, type, source, status, verification time, and provider metadata.
- Store local media ID as authoritative tool configuration, resolving it to provider media ID at runtime.

## Runtime and frontend behavior

- Registered tools show execution, handler, provider, wait mode, and schema.
- HTTP tools show endpoint, method, mapping, extraction, timeout, retry, and idempotency.
- WhatsApp tools select connection, template, language, media, and parameter mappings.

## Tests and acceptance

- Draft editing, validation, publishing, and activation work.
- Media upload/import/verify/select/send work.
- Published versions remain immutable during normal editing.

## Manual verification

- Edit both tool kinds.
- Upload/import and bind WhatsApp media.
- Execute a test call and inspect provider message evidence.

## Non-goals

- No Meta template creation workflow.

## Implementation

- Added strict `ToolConfig` support for account-scoped WhatsApp template
  settings: connection, template name, language, local media record, and
  parameter mappings.
- Added typed tool list/version/editor/validation/mutation API contracts and a
  `POST /tool-versions/{version_id}/validate` endpoint.
- Added a draft-only dashboard editor with separate registered-handler and HTTP
  controls, schema-based parameter editing, mapping controls, validation,
  saving, cloning, and publishing. Published versions remain read-only.
- Added the reusable media catalog fields `display_name`, `media_type`,
  `source`, `status`, `provider_metadata`, and `last_verified_at`.
- Added typed media list/import/upload/update/verify endpoints. Imported media
  starts unverified; upload and verify store only safe provider metadata.
- Added dashboard controls to upload media, import an existing Meta media ID,
  verify it, edit its local display name, and see provider/source/status data.
- Updated WhatsApp template generation to bind the local media record ID and to
  derive parameter mappings from the approved Meta template. Runtime resolution
  is connection-scoped and never chooses the latest catalog media implicitly.
- Added media-type validation for IMAGE, VIDEO, and DOCUMENT template headers,
  and runtime payload generation for the selected media type.
- Added migration `0022_tool_media_catalog`, including the explicitly
  development-only backfill of existing published WhatsApp tool metadata.
  The published-version guard is disabled only for that migration update and
  restored before commit.

## Verification

- Complete Python unit suite passed.
- Focused authoring/WhatsApp/evidence tests passed.
- Focused Ruff checks passed.
- `uv run alembic upgrade head` applied through `0022_tool_media_catalog`.
- OpenAPI export, dashboard contract generation, and dashboard production build
  passed.
- `alembic check` reports only the previously documented baseline drift in
  browser-session nullability, classifier JSON, inbound-webhook indexes, and
  Plan 0012 interruption JSON columns; it reports no new Plan 0014 drift.
- Development database verification shows the new media columns, explicit
  WhatsApp connection/template binding, and the published-version trigger
  enabled after migration.
- No demo or seed scripts were modified.

## Boundary

Plan 0014 is complete. Plan 0015 (provider model configuration) is the next
implementation boundary and has not been started.

## Follow-up: Meta-hosted WhatsApp media references

Status: completed

- Replace local catalog UUIDs in template tool configs with a typed
  `{format, media_id}` reference, where `media_id` is the provider's Meta ID.
- Preserve catalog UUIDs only for authenticated metadata/preview API routing.
- Upload PNG/JPEG (maximum 5 MiB) directly to Meta and retain no local binary.
- Migrate existing published/draft tool configurations and executable snapshots
  without replacing IDs or version numbers; fail if connection-scoped media
  cannot be resolved safely.
- Resolve credentials and phone-number ID from the configured integration
  connection and send the provider media ID directly in the template header.
- Add authenticated, bounded, host-validated transient preview and explicit
  Meta deletion blocked by tool and executable-run references.
- Provide image cards/picker on Integrations and tool draft editor pages, with
  safe object URL revocation.
- Remove `integration_media.source_path` only after the dry-run-first cleanup
  step confirms managed files are deleted or already missing.

Acceptance: focused adapter/config/runtime tests; migration preserves the
existing selected media and IDs; OpenAPI and generated TypeScript are current;
dashboard typecheck/build and Ruff pass. Live Meta upload/preview/delete/send
requires operator credentials and must be manually verified.

## Follow-up verification

- Added typed `header: {format, media_id}` config; `media_id` is the numeric
  provider reference. Draft create/edit/validate/publish verifies that the
  enabled WhatsApp connection owns an available media row of the expected type.
- Upload accepts only signature-checked PNG/JPEG images up to 5 MiB, sends bytes
  directly to Meta, stores safe metadata and the returned ID, and writes no local
  file. `source_path` and its setting are removed after the dry-run/apply cleanup.
- Added authenticated, no-store preview, Meta deletion with connection scoping,
  and reference checks across every tool version and executable run. Database
  row locks serialize deletion with tool authoring.
- Updated runtime to use the pinned connection's decrypted credential and put
  the configured provider ID directly in `header.parameters[].image.id` (or the
  corresponding supported video/document key). Tool result evidence includes
  the media ID and provider message ID.
- Migration `0026_meta_hosted_whatsapp_media` applied to the development DB.
  It preserved the existing v1 published tool, five bindings and selected Meta
  ID; active-run snapshot count was zero; no legacy `header_media_id` config
  keys remain; the published-version guard is enabled.
- Verification: `uv run pytest tests/unit` passed (163 tests); focused Ruff
  passed; OpenAPI export and dashboard type generation passed; dashboard
  `npm run build` passed. `alembic check` still reports the previously known
  browser-session nullability, classifier JSON, inbound-webhook indexes and
  interruption JSON drift only; no Plan 0026 media-column drift.
- The Pipecat Context Hub and runtime both report 1.11.0; no Pipecat API symbol
  or function-calling integration contract was changed. Context Hub reports an
  older refresh date, but its indexed framework version/commit match 1.11.0.
- No live Meta upload, preview, delete or WhatsApp call was made. The suite
  reports two upstream Pipecat deprecations and two pre-existing AsyncMock
  warnings in the Twilio call test.

### Manual dashboard and final-call check

1. Start the API and dashboard against the same migrated development DB. Confirm
   the WhatsApp connection is enabled and has its encrypted access token.
2. Open Integrations → WhatsApp connection → Media. Confirm the migrated
   `dialtone_followup` image card shows its Meta ID, MIME type, size and preview.
   Upload a controlled PNG/JPEG under 5 MiB; confirm Meta returns a new ID and
   no image file appears under `data/integration-media`. Verify an imported ID
   before selecting it.
3. In Tools, clone the published WhatsApp template tool to a draft. Select or
   upload the desired image, save, validate, and publish. The saved config should
   contain `{format: "IMAGE", media_id: "<Meta ID>"}`, not the catalog UUID.
   Publish/activate an agent version bound to that tool version.
4. Place a controlled final call to a test number from the dashboard. Ask the
   agent to send the approved WhatsApp template. Confirm the call recipient
   receives the image header and template body. In the run's tool evidence,
   confirm both `media_id` and the provider `message_id` match the send.
5. Try deleting an image still referenced by a draft/published tool or
   executable run; expect HTTP 409 and no Meta deletion. After unbinding/removing
   every reference, delete an unused test image and confirm it disappears from
   Meta and the catalog. Do not use production recipients or media for this test.

## Follow-up: edit WhatsApp template drafts from Tools

- Extended the existing version-aware draft editor with a WhatsApp section.
- Drafts can change the selected account-scoped catalog media and edit template
  placeholder-to-tool-argument mappings without returning to Integrations.
- Existing tool description and parameter descriptions remain the authoring
  fields for model-facing tool guidance; no additional prompt/config field is
  introduced. The editor explains where each kind of instruction belongs.
- Template identity remains fixed in this editor because changing an approved
  template can change its placeholder schema; generate a tool from Integrations
  for a different template.
