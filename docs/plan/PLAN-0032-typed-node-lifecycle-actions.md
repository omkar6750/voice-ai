---
id: PLAN-0032
title: Typed node lifecycle actions separate from classifier cadence
status: Proposed
date: 2026-09-28
related: [PLAN-0011, PLAN-0023, PLAN-0020]
---

# Typed node lifecycle actions separate from classifier cadence

## Decision

Do not merge classifier entry/exit cadence with generic action execution.
Classifier cadence is already a working runtime concern: it runs configured
entry/exit classifiers, produces classifier evidence, and injects a result into
the next node context. It must remain observable as classifier work.

The current generic `entry_actions`, `exit_actions`, and `background_hooks`
fields are misleading because they are persisted and displayed but rejected by
the live runtime. Pipecat does provide a real lifecycle-action mechanism, but
the project’s generic persisted lists do not express its typed action shape or
failure/evidence semantics. The safe rollout is:

1. immediately mark the generic fields unsupported in authoring and publish
   validation;
2. keep their data readable for migration/backward compatibility;
3. introduce a separate typed `lifecycle_actions` contract for the supported
   no-LLM-input subset;
4. execute lifecycle actions through a dedicated runner, never through
   `TracedFlowManager._set_node` or the classifier runner.

## Contract shape

Replace ambiguous lists with an explicit object in a future schema version:

```python
class LifecycleAction(ConfigModel):
    tool_id: Identifier
    phase: Literal["before_node", "after_node"]
    input_mode: Literal["resolved_context"] = "resolved_context"
    timeout_secs: float = Field(default=10, gt=0, le=60)
    failure_policy: Literal["fail_node", "continue"] = "continue"
    idempotency_key: str | None = None
```

The tool registry must separately declare:

```python
lifecycle_safe: bool
requires_llm_arguments: bool
side_effect_class: Literal["none", "external_write"]
```

Only `lifecycle_safe == true` and `requires_llm_arguments == false` tools may
be selected. Contact, run, node, and resolved configuration values may be
provided by the runtime context; arbitrary LLM arguments may not be invented.
`background_hooks` are not lifecycle actions: they require a job/scheduler
owner and should remain unsupported until that subsystem exists.

## Current boundary

`FlowNodeConfig.entry_actions` and `exit_actions` are validated and persisted;
`NativePipelineHost.prepare()` rejects them. The dashboard exposes them in
`FlowPanel.tsx`, `ToolsPanel.tsx`, and `AgentEditorPage.tsx`. Classifier entry and
exit are executed in `TracedFlowManager._set_node` through
`_classifier_runner("exit", current_node)` followed by
`_classifier_runner("entry", node_id)`.

Do not add action dispatch to `_set_node`. Add a `LifecycleActionRunner` seam
that receives a node transition event:

```python
await lifecycle_runner.before_node(node_id, runtime_context)
await flow_manager.set_node(node_id, node_config)
await lifecycle_runner.after_node(node_id, runtime_context)
```

The runner owns timeout, idempotency, tool evidence, and failure policy. The
flow manager owns node state. The classifier runner owns classifier context
delivery. Those three responsibilities must not share a mutable “actions”
list.

## Pipecat mapping

Official Pipecat Flows documentation defines `pre_actions` as running on node
transition before LLM inference and `post_actions` as running after inference
and TTS finishes. It includes built-in `tts_say` and `end_conversation`, plus a
`function` action that runs a named handler inline. This supports the proposed
separate lifecycle runner, but not arbitrary database tool names: the adapter
must translate a typed project action into a known Pipecat action and keep
classifier evidence separate.

Reference: [Pipecat Flows actions](https://docs.pipecat.ai/pipecat/flows/actions).

Initial allow-list recommendation:

- `tts_say`: only static/resolved text, explicit context append behavior;
- `end_conversation`: only as a post-action or explicit terminal action;
- project `function` actions: only registry entries marked lifecycle-safe,
  no required LLM arguments, bounded execution, and explicit idempotency.

Do not expose Pipecat’s generic `function` action directly as an arbitrary
user-selected tool. It is a runtime handler name, not proof that a persisted
tool is safe at a node boundary.

## Safe rollout

### Phase 1: remove misleading runtime surface

- Add a capability flag/validation result saying generic lifecycle actions are
  unsupported by the active runtime.
- Reject them at draft/publish time with the exact field and reason.
- Keep old values when reading old drafts, but prevent new values from being
  saved unless migrated.
- Hide or visibly disable the dashboard controls and link to the capability
  message.
- Keep classifier entry/exit controls unchanged.

### Phase 2: introduce typed lifecycle actions

- Add the typed contract and a registry capability check.
- Resolve actions from the immutable runtime snapshot.
- Run `before_node` only after the prior node has safely completed and before
  the new node is exposed to the LLM.
- Run `after_node` only after final response/playback semantics defined by the
  call lifecycle plan; do not pretend “tool returned” means “audio played”.
- Emit a lifecycle-action span/result with node, phase, tool version,
  idempotency key, duration, outcome, and redacted error.

### Phase 3: migration and UI

- Provide a one-time draft migration from legacy lists only when each tool is
  allow-listed and has no required LLM arguments.
- Preserve unconvertible legacy references as publish errors, not silently
  dropped behavior.
- Show timing, failure policy, and capability status in the editor.

## Failure and retry rules

- `before_node` failure with `fail_node` prevents node entry and produces a
  failed transition, not a classifier failure.
- `continue` records failure and allows the node to run.
- External writes require an idempotency key and must not retry blindly.
- A transition retry must not run the same lifecycle action twice unless its
  registry metadata explicitly declares it idempotent.
- Action evidence must identify lifecycle phase separately from tool-call and
  classifier evidence.

## Tests

- legacy action fields are rejected at publish and never reach live prepare;
- classifier entry/exit still runs once per transition;
- classifier output remains separate from lifecycle-action evidence;
- allow-listed no-input action receives resolved context only;
- required LLM-argument tool is rejected;
- timeout and failure policies behave deterministically;
- duplicate transition does not duplicate an idempotent action;
- external-write action requires an idempotency key;
- old drafts round-trip without silently losing unsupported references;
- dashboard capability state matches runtime capability metadata.

## Non-goals

- No arbitrary action execution from persisted tool names.
- No background scheduler implementation.
- No classifier redesign.
- No automatic callback execution.
- No action execution added directly to `native.py` or `FlowManager`.

## Acceptance criteria

- Users cannot configure a control that the live runtime silently rejects.
- Classifier cadence remains a distinct, tested module.
- Any future lifecycle action has explicit inputs, timing, timeout, retry,
  evidence, and capability semantics.
- The runtime has one action runner seam rather than branching action behavior
  throughout node transitions.
