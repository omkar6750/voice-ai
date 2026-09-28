# ADR-0014 · Versioned tool authoring and account-scoped WhatsApp media

Status: Accepted  
Date: 2026-09-27  
Related: [PLAN-0014](../plan/PLAN-0014-tool-and-whatsapp-authoring.md),
[ADR-0006](ADR-0006-versioned-configuration.md),
[ADR-0007](ADR-0007-exchanges-and-integration-secrets.md),
[ADR-0009](ADR-0009-canonical-tool-registry-and-db-cleanup.md)

## Context

The tool dashboard could inspect versions but could not edit drafts. It also
rendered HTTP-only fields for registered tools as `Not applicable`, which made
the execution model ambiguous. WhatsApp template generation accepted a provider
media ID directly and the runtime could silently select the newest catalog media,
so a published tool was not bound to a stable local media record or account.

The existing database already had a reusable `integration_media` table, but it
only stored filename, provider ID, MIME type, availability, and upload/check
timestamps. It did not represent a display name, media kind, import source,
verification state, or safe provider metadata.

## Decision

Use a single strict `ToolConfig` contract for all tool versions and expose a
version-aware editor that only writes drafts. Published versions remain
immutable during normal API operation:

```text
published version
        │ clone
        ▼
draft ToolVersion
        │ edit → validate → publish
        ▼
published ToolVersion
```

The editor renders two execution forms:

- Registered: reviewed handler, provider/execution description, wait mode,
  acknowledgement, and function parameter schema.
- HTTP: endpoint, method, timeout, secret reference, request argument mapping,
  response extraction, and retry settings.

The editor does not provide a raw JSON-only workflow. Advanced mapping fields
use line-oriented `source -> destination` controls while ordinary parameters
use typed rows.

## WhatsApp configuration contract

`send_whatsapp_template` requires an account-scoped block:

```text
whatsapp:
  connection_id
  template_name
  language
  header_media_id       # local IntegrationMedia.id, not Meta's provider ID
  parameter_mappings    # template placeholder index -> tool argument name
```

`header_media_id` is deliberately local. At execution time the native host
resolves:

```text
ToolConfig.whatsapp.header_media_id
        │
        ▼
IntegrationMedia(connection_id, id, status=available)
        │
        ▼
provider_media_id + media_type
        │
        ▼
Meta template message payload
```

The runtime no longer chooses the latest media record as an implicit header.
Missing or unavailable configured media is a non-retryable tool-configuration
diagnostic. Template generation validates that selected media belongs to the
same connection, is available, and matches IMAGE, VIDEO, or DOCUMENT template
header format. The runtime emits the corresponding WhatsApp header parameter
type instead of assuming `image`.

## Media catalog model

The catalog remains owned by the WhatsApp integration connection. The current
schema is:

```text
IntegrationMedia
  connection_id
  provider_media_id
  display_name
  filename
  media_type: image | video | document | audio
  mime_type
  size_bytes
  sha256?
  source_path?
  source: uploaded | imported
  status: available | unverified | unavailable | deleted
  provider_metadata       # filtered, non-secret fields only
  uploaded_at
  last_verified_at?
```

Uploads are immediately available after a successful Meta upload and record a
safe provider ID/type summary. Imported IDs begin as `unverified`; the verify
endpoint calls Meta, updates status/timestamp/type/size/hash when returned, and
filters provider metadata so URLs and credentials are not stored. Local display
name editing never changes the provider ID.

## API and generated-contract flow

The new API responses and request bodies are Pydantic models. The contract path
is unchanged:

```text
Pydantic models
  → FastAPI response models
  → scripts/export_openapi.py
  → data/openapi.json
  → dashboard npm run generate
  → generated TypeScript components
  → typed tool/media UI
```

New typed surfaces include tool version responses, tool validation, media list
and mutation responses, generated WhatsApp tool responses, and the draft
validation endpoint. The dashboard imports generated schema types rather than
creating duplicate API DTOs.

## Migration and development data

Migration `0022_tool_media_catalog` renames the old media availability/check
columns to `status`/`last_verified_at`, adds the catalog metadata, backfills
existing rows, and adds current-value checks. It also backfills the existing
development `send_whatsapp_template` version with the active WhatsApp
connection and template name. Because this is an explicitly authorized
development migration that mutates a published row, it temporarily disables
only the `tool_versions.guard_published` trigger around that data update and
restores it before commit. Normal API editing still rejects published writes.

## Runtime and UI behavior

Tool cards show registered execution as handler/provider information and show
endpoint/method only for HTTP tools. Draft cards expose Edit, Save, Validate,
and Publish. Published cards expose Clone draft. The WhatsApp integration UI
provides upload, import existing Meta ID, verify, local metadata edit, and a
template-tool form whose media selector stores the local catalog ID.

## Verification and limitations

- Complete unit suite, focused authoring tests, and Ruff checks pass.
- Migration head is `0022_tool_media_catalog` and the restored published guard
  is enabled.
- OpenAPI export, generated TypeScript, and dashboard production build pass.
- `alembic check` retains only baseline drift documented by earlier plans.
- Live Meta upload/verify/send still requires configured credentials and a real
  WhatsApp connection; no external message was sent by automated tests.
- Meta template creation remains out of scope; this only configures existing
  approved templates.

## Follow-up decision: edit WhatsApp bindings on tool drafts

The integration Templates workflow remains the place to discover approved Meta
templates and create the first tool definition. After cloning that definition,
the Tools draft editor also permits changing its account-scoped catalog media and
template-placeholder-to-tool-argument mappings. Template name/language remain
pinned there: changing template identity can change the provider-defined
placeholder schema and must go through template generation.

No extra free-form prompt field is added to `ToolConfig`. The existing tool
`description` and each parameter's schema `description` are the model-facing
instructions: the runtime passes them as the function description and parameter
descriptions in `FlowsFunctionSchema`. Agent-wide behavior belongs in the agent
system/role prompt. For approved WhatsApp templates, Meta owns the literal body;
the model supplies mapped placeholder values and cannot rewrite the template.
Wait-mode and acknowledgement fields are retained only for reading existing
published configurations; the current runtime does not speak the configured
acknowledgement or implement background continuation. The dashboard therefore
does not offer those ineffective controls. Tool descriptions and input
parameter descriptions are passed to Pipecat as function schema metadata and
are the tool-specific guidance the model receives.

The editor clarifies these boundaries and preserves local media IDs in the draft;
runtime media resolution remains connection-scoped as described above.
