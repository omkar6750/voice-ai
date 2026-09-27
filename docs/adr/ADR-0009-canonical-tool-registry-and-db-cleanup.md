---
id: ADR-0009
title: Canonical runtime tool registry and conservative development cleanup
status: Accepted
version: 1
date: 2026-09-27
related: [RFC-0003, ADR-0006, ADR-0007, PLAN-0009]
---

# Context

Tool support was represented in two places: a hard-coded API catalog and conditional
branches in the native host. Database tool versions could therefore claim a handler
without an explicit capability check. The development database also accumulated draft
tool versions that were not referenced by an agent or historical evidence.

The database currently contains historical agent versions used by runs and tool
versions used by tool invocations. Removing those records would damage the evidence
model described by ADR-0007.

# Decision

Create one typed runtime capability registry in the shared runtime contracts package.
The registry describes supported registered handlers and is used by API validation and
native pipeline preparation. Registered tools must name a handler in this registry;
HTTP tools remain governed by `ToolConfig`'s URL, method, retry, timeout, and secret
reference validation.

Expose a typed validation report at `GET /tools/validation`. The report is read-only,
deterministic, and checks:

- tool schema validity and logical-tool/config-name ownership;
- registered handler capability membership;
- agent schema validity;
- JSON config binding and relational binding parity;
- tool owner/version consistency;
- published agents using only published tools;
- active version ownership and publication state; and
- unreferenced draft tool versions eligible for development cleanup.

Expose `POST /tools/validation/cleanup` with an explicit `{ "apply": true }` opt-in.
The API cleanup remains conservative and removes only draft tool versions that have no
agent binding and no historical tool invocation. It is safe to repeat.

For the current development workspace, the operator separately authorized a one-time
history reset. That reset deleted all run/evidence history, retained the three logical
agents and their active versions, deleted all non-active agent versions, and retained
one published tool version per logical tool plus any active bindings. This is a
development-only data operation, not normal API cleanup behavior.

# New contracts and data flow

```text
ToolVersion.config.handler
        -> RegisteredHandlerSpec registry
        -> API validation report
        -> native host prepare() guard
```

```text
POST /tools/validation/cleanup {apply:false}
        -> report only

POST /tools/validation/cleanup {apply:true}
        -> delete unreferenced draft ToolVersion rows
        -> re-run validation
        -> return cleaned IDs and remaining issues
```

All new API responses and requests use Pydantic models. OpenAPI is regenerated and the
dashboard's generated TypeScript contract is rebuilt as part of verification.

# Runtime behavior

The native host still dispatches through its existing handler implementations, but it
now fails before pipeline construction when a resolved registered definition claims an
unknown handler. This keeps unsupported tools from silently reaching the generic
"adapter is not connected" fallback.

# UI/API behavior

The existing handler catalog remains available for authoring. The new validation
endpoint provides the authoritative diagnostics and cleanup candidates to the future
tool-authoring UI. This ADR does not add the editor or WhatsApp media controls; those
belong to Plan 0014.

# Verification

- Local database validation returned `valid=True` with four unreferenced draft
  WhatsApp candidates and no active binding errors.
- Focused tests passed: 19.
- Ruff passed for changed backend/runtime/test files.
- OpenAPI export, dashboard type generation, and dashboard production build passed.

# Known limitations

- The cleanup endpoint does not remove historical published versions automatically;
  the explicit development reset was authorized for this workspace only.
- The existing `/tools/handlers` response is still a legacy presentation catalog;
  Plan 0014 will replace its authoring surface with the registry-backed editor.
- The local development database was reset after implementation at the user's explicit
  request. It now has zero runs, three logical agents with one active version each,
  twelve published tool versions, and no cleanup candidates.
