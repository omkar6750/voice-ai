---
id: PLAN-0022
title: Node-scoped flow transition tool schemas
status: Executed
date: 2026-09-28
related: [RFC-0003, ADR-0006, ADR-0019]
---

# Goal

Advertise only the flow destinations permitted by the current node, using the
shared Pipecat function-schema path for every LLM provider.

## Implementation

- Copy each tool's parameter properties before adapting them to `FlowsFunctionSchema`.
- Set `change_node.node.enum` to the current node's `transitions`.
- Do not advertise `change_node` on nodes with no outgoing transitions.
- Keep the runtime transition check as the authoritative safety guard.

## Verification and acceptance

- Per-node enum and serialized `FunctionSchema` checks pass.
- Shared published tool definitions remain unchanged across node construction.
- A no-transition node advertises no `change_node` function.
- Runtime continues to reject an invalid transition.
- Verified with 12 focused tests and Ruff; the dashboard is unaffected.

## Non-goals

No provider-specific schemas, database changes, prompt rewrites, or provider calls.
