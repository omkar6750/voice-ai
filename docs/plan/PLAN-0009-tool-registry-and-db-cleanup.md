# PLAN-0009 · Canonical tool registry and development database cleanup

Status: completed

## Existing facts

- Registered handlers are selected inside `NativePipelineHost` conditionals.
- Database bindings include stale and mismatched classifier names.
- Published tool and agent versions are currently versioned, but development cleanup may remove obsolete versions after repair.

## Scope

- Create an introspectable runtime handler registry.
- Validate database tool bindings against runtime handlers.
- Repair the active development configuration through draft, validation, publish, and activation.
- Remove obsolete versions and stale bindings after repair.

## Contracts

- Add typed validation report models.
- Registered tools require a handler present in the runtime registry.
- HTTP tools require a valid URL, method, mapping, and retry policy.

## Runtime and frontend behavior

- Registry metadata is available to API validation and tool authoring.
- Registered tools display handler/provider execution metadata.
- HTTP tools display endpoint/method metadata.

## Tests and acceptance

- Every active binding resolves.
- Every registered handler exists.
- Repeated validation is idempotent.
- Obsolete development versions and bindings are removed only after references are repaired.

## Manual verification

- Run the dry-run validation report.
- Inspect invalid and stale bindings.
- Apply cleanup.
- Verify one current configuration remains per logical agent/tool.

## Non-goals

- No changes to demo or seed scripts.
- No compatibility layer for obsolete database shapes.

## Implementation result

- Added the shared runtime `RegisteredHandlerSpec` registry and helper functions in
  `packages/voice_runtime/voice_runtime/contracts/registry.py`.
- The native host now rejects a registered tool whose handler is absent from that
  registry before constructing the live pipeline.
- Added typed validation contracts and `GET /tools/validation`, plus an explicitly
  opt-in `POST /tools/validation/cleanup` endpoint.
- Validation checks tool schema/owner/name/handler integrity, agent schema integrity,
  relational/config binding parity, published-agent-to-published-tool rules, active
  version ownership, and unreferenced draft candidates.
- The operator-authorized development reset was then applied to the local database:
  all run/evidence history was removed, each logical agent was retained with only its
  active version, and unneeded draft tool versions were removed. The reset used the
  repository's existing controlled trigger-bypass pattern because published-version
  immutability guards are intentionally enabled in normal API writes.
- No demo or seed script was changed.

## Verification evidence

- Before reset, the local database report was `valid=True` with four cleanup
  candidates, all unreferenced draft WhatsApp tool versions. Ten historical agent
  versions and all 33 runs/evidence records were then removed at the user's explicit
  direction. Three logical agents and their active configurations were preserved, and
  twelve published tool versions remain in the catalog.
- After reset: `runs=0`, `tool_invocations=0`, `agent_versions=3`,
  `agent_version_tools=10`, and validation is `valid=True` with no cleanup candidates.
- `uv run ruff check` passed for all changed Plan 0009 files.
- Focused runtime/API suite passed: 19 tests.
- `uv run python scripts/export_openapi.py` passed.
- `npm run generate` and `npm run build` passed in `apps/dashboard`.

## Boundary

Plan 0009 is complete. Plan 0010 (tool-result delivery evidence) has not been started.

## Follow-up: deleting a tool with saved agent references

- Tool deletion now removes the deleted tool's binding and explicit prompt
  directives from every agent version, including published versions in this
  development workspace; affected revisions are incremented.
- Cleaned references include global/node/role prompts, node tool bindings,
  entry/exit actions, and background hooks, including alias binding keys pinned
  by the deleted tool ID/version ID.
- Historical tool invocation rows are retained; their nullable
  `tool_version_id` is cleared before deleting the tool definition so evidence
  is not orphaned from the database's referential model.
- A recreated tool is a new identity and is not silently rebound. Agent authors
  must explicitly bind the new version and add its prompt directive.
- The development agent versions in the reported 500 response were repaired;
  all five now validate with no reference to the deleted WhatsApp tool.
