# ADR-0022 · Meta-hosted WhatsApp media references

Status: Accepted
Date: 2026-09-28
Related: [ADR-0007](ADR-0007-exchanges-and-integration-secrets.md),
[ADR-0014](ADR-0014-tool-and-whatsapp-authoring.md),
[PLAN-0014](../plan/PLAN-0014-tool-and-whatsapp-authoring.md)

## Context

The WhatsApp media catalog previously stored both Meta's reusable media ID and
a local `source_path`. Template tool versions stored a local catalog UUID and
the runtime had to query the catalog to resolve that UUID at send time. The
dashboard's preview could not be authenticated by a plain `<img>` request
because the operator bearer token exists only in browser memory. The runtime
also cleared the tool's configured connection ID during credential lookup,
which could prevent the selected integration from being used.

## Decision

`IntegrationMedia` remains a connection-scoped metadata catalog. It stores the
provider media ID, display name, filename, MIME type, byte size, checksum,
status, source, and safe provider metadata, but no local media bytes or path.
New image uploads are PNG/JPEG, at most 5 MiB, uploaded directly to Meta. The
request bytes are used only transiently for upload and checksum computation.

WhatsApp template tool configuration now uses:

```json
{
  "connection_id": "<integration-connection-id>",
  "header": { "format": "IMAGE", "media_id": "<meta-provider-media-id>" }
}
```

The local catalog UUID is only an internal API route key for listing and
authenticated previews. The runtime pins the configured connection, decrypts
that connection's access token, and sends the configured Meta ID directly as
`template.components[].parameters[].image.id`. The result evidence includes
the exact media ID and provider message ID.

The authenticated preview endpoint fetches fresh metadata from Meta, validates
the returned URL's HTTPS scheme and Meta-controlled host, validates image MIME
type, enforces a 5 MiB stream bound, and never stores the temporary URL or
image bytes. The dashboard uses its in-memory bearer token to fetch a Blob,
renders an object URL, and revokes that URL on dependency changes/unmount.

Meta deletion is an explicit user action. It is rejected while any tool version
or queued/claimed/running/uncertain run snapshot references that connection and
media ID. The catalog row is removed only after Meta confirms deletion or the
provider reports the media already absent.

## Migration and cleanup

Migration `0026_meta_hosted_whatsapp_media` converts legacy local catalog UUIDs
to provider IDs and explicit header formats for every draft/published template
tool and executable nonterminal run snapshot. It validates connection ownership
and media availability and aborts rather than guessing. Existing agent, tool,
binding IDs and version numbers are preserved. The migration removes only the
`integration_media.source_path` column; it does not alter demo or seed scripts.

Before migration, `scripts/cleanup_whatsapp_media_files.py` is dry-run by
default. `--apply` deletes only exact file paths resolving below
`data/integration-media`, reports missing paths, and leaves unsafe/out-of-root
paths and symlinks untouched. Migration 0026 refuses to drop `source_path`
while any row still contains a pointer, requiring cleanup first. The existing
selected file was already missing at migration time, so there was no local
image file to remove.

Tool create/edit/validate/publish operations check the connection and catalog
reference against the database. Those checks take a row lock on selected media;
deletion locks the same catalog row before checking all tool versions and live
snapshots, then holds the lock until Meta confirms deletion and the catalog row
is removed. This prevents a concurrent draft/publish from introducing a new
reference between the check and provider deletion.

## Verification and limitations

- Focused API/runtime/media tests cover contract validation, provider ID header
  serialization, safe preview URL/MIME/size checks, and idempotent deletion.
- OpenAPI export and dashboard type generation/typecheck/build validate the
  public contract and picker UI.
- Development DB migration preserved the selected media, published tool ID and
  version, all five bindings, and re-enabled the published-version guard.
- `uv run pytest tests/unit` passed (163 tests); changed-file Ruff passed.
- Alembic reports only previously documented baseline drift; no media-path
  schema drift remains.
- No live Meta media upload, preview, deletion, or message was performed by
  automated tests; those require the configured WhatsApp credentials.
- Imported non-image catalog entries remain representable for existing template
  media formats; the new upload/picker preview workflow is image-focused.
