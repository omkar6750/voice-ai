# Handoff 002: node entry/exit actions and classifier cadence

## Objective

Decide whether generic `entry_actions`, `exit_actions`, and
`background_hooks` should be removed, or whether a small safe subset should be
implemented for tools thjat done require main agents input  . Preserve classifier entry/exit cadence as a
separate concern unless research proves a clean shared model.

## Current implementation

Contracts:

- `packages/voice_runtime/voice_runtime/contracts/agent.py`
  - `FlowNodeConfig.entry_actions`
  - `FlowNodeConfig.exit_actions`
  - `AgentConfig.background_hooks`
- `packages/voice_runtime/voice_runtime/contracts/cadence.py`
  - classifier node entry/exit configuration

Runtime:

- `packages/voice_runtime/voice_runtime/execution/native.py`
  - `NativePipelineHost.prepare()` rejects generic actions and background hooks;
  - `NativePipelineHost._run_node_classifier()` runs configured classifiers;
  - `TracedFlowManager._set_node()` invokes classifier exit/entry checkpoints.

Dashboard:

- `apps/dashboard/src/pages/agents/FlowPanel.tsx`
- `apps/dashboard/src/pages/agents/ToolsPanel.tsx`
- `apps/dashboard/src/pages/agents/AgentEditorPage.tsx`

The current classifier path is separate from generic actions:

```python
if current_node and current_node != node_id:
    await self._classifier_runner("exit", current_node)
await self._classifier_runner("entry", node_id)
```

Generic action lists are persisted and validated for references, but live calls
reject them at `prepare()`.

## Web-research instructions

The research agent has no repository or CLI access. Search official Pipecat
Flows documentation and public source for node entry/exit hooks, pre/post
actions, `FlowManager`, tool execution, and `end_conversation`. The key design
question is whether Pipecat lifecycle actions are equivalent to arbitrary
application tools. Do not assume that a similarly named Pipecat feature maps to
this project’s persisted action lists.

Determine:

1. Whether Pipecat actions are intended for arbitrary function tools or only
   built-in lifecycle actions.
2. Whether an action can safely run without an LLM tool call and how its result
   enters context/evidence.
3. How an action failure affects node entry, node exit, and call completion.
4. Whether classifier cadence can share an internal lifecycle hook without
   making classifier output look like a tool action.
5. Which no-input tools are safe candidates, if any.
6. Whether unsupported action fields should be removed from the active contract
   or rejected at draft/publish time.
7. Whether no-input actions can be idempotent, timeout-bounded, observable, and
   safely retried without an LLM-generated tool call.

## Required deliverable

Return one recommended direction:

- remove the generic fields;
- keep them but mark them unsupported;
- or implement a typed allow-list.

Include the resulting contract shape, dashboard behavior, evidence model,
failure semantics, migration requirements, and tests. Do not merge classifier
cadence and generic action evidence without explaining the distinction.
Include source links and identify any conclusion that is an architectural
recommendation rather than a documented Pipecat guarantee.
