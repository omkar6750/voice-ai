# Research handoffs

These documents are prepared for dedicated web-research agents. The research
agent has no repository, filesystem, CLI, Context Hub, or code-execution access.
The inline snippets and summaries are the available implementation context.
The paths are included only so a later implementation agent can locate the
changes.

No external research is included here. Research must use public web sources:
prefer official Pipecat, Twilio, browser/WebRTC, and provider documentation;
use source code, changelogs, and issue discussions only when official docs do
not answer the lifecycle question. Record URLs, documentation versions or
access dates, and clearly label assumptions.

## External research handoffs currently in use

1. [Provider and Pipecat runtime capability audit](./HANDOFF-003-provider-runtime-audit.md)
2. [Token usage, metrics, pricing, and cost UI](./HANDOFF-004-token-pricing.md)

These are self-contained briefs for external agents. They do not require the
agent to open the repository paths mentioned as implementation references.

## Implementation plans prepared in this repository

The remaining topics are planned locally from the actual codebase:

1. [Typed call outcomes and transport-safe termination](../plan/PLAN-0031-call-outcome-and-termination-state-machine.md)
2. [Typed node lifecycle actions](../plan/PLAN-0032-typed-node-lifecycle-actions.md)
3. [Fact-based run reconciliation](../plan/PLAN-0033-reconciliation-and-transport-release.md)

The older HANDOFF-001, HANDOFF-002, and HANDOFF-005 files are retained as
background notes only; implementation should follow PLAN-0031 through
PLAN-0033.

## Deferred, not ready for research

- Live WebSocket monitoring: wait for the Clerk worktree.
- Automatic callback execution: wait for production/Clerk readiness.
- Historical database run deletion: local evidence/recording cleanup is complete;
  database deletion needs a separate retention and cascade decision.

## Straightforward remaining implementation TODOs

- Keep `VOICE_API_BASE_URL` documented and configure it in deployed environments.
- Decide whether to remove or visibly disable unsupported action controls after
  PLAN-0032.
- Fix the unused exception binding reported by Ruff (`F841`).
- Add regression coverage for the injected snapshot used by
  `TracedFlowManager`.
- Re-run the full test suite with an isolated writable pytest temp directory.
- Investigate the remaining Vite Windows access failure after TypeScript passes.
