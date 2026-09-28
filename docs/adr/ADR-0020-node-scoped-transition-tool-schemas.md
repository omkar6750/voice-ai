# ADR-0020: Node-scoped transition tool schemas

Status: Accepted

## Context

The saved flow graph already defines each node's permitted `transitions`, and the
runtime rejects a `change_node` request outside that list. However, the LLM-facing
function schema previously described `node` as an unconstrained string, allowing
models to propose invalid targets before the runtime guard rejected them.

## Decision

At native `NodeConfig` construction, build a fresh copy of the bound tool property
schema. For `change_node`, constrain the `node` property with an enum copied from
the current node's transitions. Do not mutate the published tool definition or
reuse a mutable schema across nodes. If a node has no outgoing transitions, omit
`change_node` from that node's functions and prompt-reference compilation.

The runtime transition check remains authoritative; the enum is guidance and
provider-neutral validation, not a replacement for runtime validation. All
providers receive the same Pipecat `FlowsFunctionSchema` and serialized
`FunctionSchema` contract.

## Consequences

Each inference sees only legal destinations for its current node, while tool
definitions shared across nodes remain unchanged. Terminal/no-transition nodes
cannot advertise a transition function. Providers that ignore JSON Schema enums
remain safe because the runtime guard is retained. Tests cover per-node schemas,
serialization, non-mutation, omission, and invalid-target rejection.
