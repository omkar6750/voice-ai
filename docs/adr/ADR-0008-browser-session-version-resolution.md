# ADR-0008 · Browser-session version resolution and idempotent cleanup

Status: Accepted (transport/handler details superseded by ADR-0021)
Date: 2026-09-27
Related: [PLAN-0008](../plan/PLAN-0008-browser-session-regression.md), [ADR-0006](ADR-0006-versioned-configuration.md), [ADR-0007](ADR-0007-exchanges-and-integration-secrets.md)

## Context

The browser test-call path accepted an optional `agent_version_id`, but when the dashboard did not provide one it selected the newest published `AgentVersion` globally. That allowed a browser test for one agent to execute another agent when the other agent had a newer version.

Browser transport disconnects only marked the in-memory context ended. Explicit cleanup and pipeline finalization could also race, and evidence delivery cancellation was not awaited.

## Decision

Browser-session creation now accepts both `agent_id` and `agent_version_id`.

- An explicit version is accepted only when it belongs to the selected agent, when an agent is supplied.
- Without an explicit version, the service resolves the selected agent's active published version, then that agent's latest published version.
- A request without an explicit version must identify an agent.
- No query may select an unrelated agent's version globally.

Runtime cleanup is centralized in `BrowserSessionContext.close_runtime()`:

- An async lock prevents duplicate cleanup.
- The pipeline task is cancelled and awaited when cleanup is initiated externally.
- The pipeline task does not cancel itself during its own `finally` block.
- Host and WebRTC request-handler resources are closed once.
- Transport-originated disconnects trigger database finalization through a background task.
- Evidence delivery cancellation is awaited.

## API and frontend changes

- `CreateBrowserSessionRequest.agent_id` is optional for schema compatibility but required when `agent_version_id` is omitted.
- `TestAgentModal` sends the selected agent ID with the selected version ID.
- Existing browser-session response shape remains unchanged.

## Verification

- Added tests for cross-agent version rejection.
- Added tests for selected-agent fallback.
- Added tests for missing-agent rejection.
- Added idempotent cleanup assertions.
- Browser-session and API tests: 19 passed.
- Ruff passed for changed backend and test files.
- OpenAPI export passed.
- Dashboard type generation passed.
- Dashboard production build passed.

## Known limitations

- The existing frontend still contains unrelated handwritten DTOs outside this plan's scope.
- No live WebRTC hardware/browser session was executed in this change; manual verification remains required.
