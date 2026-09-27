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
