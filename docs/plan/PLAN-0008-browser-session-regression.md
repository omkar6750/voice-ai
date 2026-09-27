# PLAN-0008 · Browser session version resolution

Status: completed

## Existing facts

- `TestAgentModal` sends an agent/version selection for browser test calls.
- The browser session service can fall back to the newest published `AgentVersion` globally.
- This can run a different agent from the one selected in the dashboard.
- Browser disconnect cleanup does not currently prove host/request-handler/evidence finalization is complete.

## Scope

- Resolve the requested agent and version deterministically.
- Remove global newest-version fallback.
- Make browser disconnect cleanup idempotent and observable.

## Contracts

- Preserve the existing browser-session request shape unless a typed response change is required.
- Return a deterministic 4xx error for an invalid or stale requested version.
- Keep selected agent identity in the resolved run snapshot.

## Runtime and frontend behavior

- Explicit version: run that version when it is allowed for the browser test.
- No explicit version: use the selected agent's active published version, then that agent's latest published version if the product contract permits it.
- Never select a version belonging to another agent.
- Browser disconnect closes the host, request handler, transport, and evidence delivery exactly once.

## Tests and acceptance

- Selected Agent A runs even when Agent B has a newer version.
- Explicit version selection is honored.
- Invalid version returns a deterministic error.
- Browser disconnect finalizes cleanup once without duplicate evidence or exceptions.
- Existing browser-session tests remain green.

## Manual verification

- Select two agents with different latest versions in the dashboard.
- Start a browser test for the older agent.
- Confirm the run snapshot and timeline identify the selected agent/version.
- Close the browser session and confirm the run reaches a terminal state.

## Non-goals

- No changes to `scripts/demo_call.py` or seed scripts.
- No redesign of browser UI beyond displaying deterministic request errors.

## Implementation result

- Added `agent_id` to browser-session creation and sent it from the dashboard.
- Explicit versions are rejected when they belong to another agent.
- Version fallback is scoped to the selected agent and requires a published version.
- Removed the global newest-agent-version fallback.
- Browser runtime cleanup is guarded by an async lock and is safe across explicit end requests, transport disconnects, and pipeline finalization.
- Transport disconnects now trigger asynchronous database/session finalization.
- Evidence delivery cancellation is awaited during browser pipeline cleanup.

## Verification

- `uv run pytest tests/unit/test_browser_sessions.py tests/unit/test_api.py` — 19 passed.
- `uv run ruff check apps/api/voice_api/services/browser_session_service.py apps/api/voice_api/schemas/browser_session.py apps/api/voice_api/api/v1/endpoints/browser_sessions.py tests/unit/test_browser_sessions.py` — passed.
- `uv run python scripts/export_openapi.py` — passed.
- `npm run generate` from `apps/dashboard` — passed.
- `npm run build` from `apps/dashboard` — passed.
