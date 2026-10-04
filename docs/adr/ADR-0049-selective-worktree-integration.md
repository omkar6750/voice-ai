# ADR-0049: Selective worktree integration

Status: Accepted locally, 2026-10-03.

## Decision

Adapt useful changes from the read optimization, latency tracing and SIM7600
diagnostics worktrees into the current flow/runtime branch. Preserve current
agent editing, classifier contracts, text tests and the separate runtime.
No branch-wide merge, rebase, main update or deployment is part of this change.

Reuse the official backend Clerk SDK and pooled HTTP clients. Every protected
request still verifies its token and performs live membership authorization.
There is no 15-second authorization cache. The React ClerkProvider remains the
browser instance owner. Release read-only preliminary DB transactions before
waiting for remote membership, so authorization latency does not occupy a pool
connection. Close clients at API shutdown.

Runs use bounded tenant-scoped keyset pagination and projections. Version lists
can request summaries; editing fetches only the selected full configuration.
Background reads preserve local edits and cannot advance the draft's save
revision silently. Persist only an explicit allowlist of catalog/run summaries
in a bounded per-user session cache, excluding support-session data and prompts.

Development diagnostics use fixed metadata and the existing bounded safe logger.
SIM7600 serial cancellation waits for the in-flight worker before releasing its
lock. Diagnostic disk writes occur on a bounded worker. Cleanup must confirm
both transport and host release before allowing device reuse. Expired runtime
leases are marked uncertain on authorized reads; matching late confirmed cleanup
can reconcile them. Recovery never dials or starts a replacement call.

## Consequences

The runs API returns one page (25 by default, at most 100), plus has_more and
next_cursor. Clients needing older runs must follow cursors. Text tests remain
excluded. Migration 0047_dashboard_read_index follows 0046_text_tests in the
existing linear migration chain.

Storybook and stale UI, runtime ownership and membership caches are excluded.
Provider/hardware acceptance remains an operator task. See the integration
report for provenance, checks and local operating steps.
