# Pipecat Flows audit checklist

This checklist records the questions and proposed changes from the 2026-10-01 conversation. The answers live in `questions-answers/`; implementation work, if agreed, will be broken down in `plans/`.

## Documentation and architecture

- [x] Preserve all six supplied Pipecat documents verbatim in `references/` and identify each source.
- [x] Read the complete Pipecat documentation index before exploring other live documentation.
- [x] Read the current Flows, flow config, nodes/messages, functions, state, actions, context strategies, pipeline, runner, worker, provider, and VAD documentation relevant to this audit.
- [x] Determine whether our flow is declarative YAML/config, programmatic, or a custom graph and whether a Pipecat `FlowManager` is created and initialized for calls.
- [x] Trace how a published agent/config reaches the call runner and which parts of that configuration are actually applied.
- [x] Provide a representative, validated illustrative YAML and distinguish it from an unavailable Elevated Box export.
- [ ] Export and validate the actual Elevated Box published configuration when its snapshot is available.

## Messages, context, and model mapping

- [x] Trace every prompt injected into the LLM context, its role, and its lifecycle; verify the reported node prompts sent as `user`.
- [x] Explain current global system instruction versus per-node role and task messages.
- [x] Explain how Pipecat role and task messages behave on APPEND and RESET, including replacement or persistence on transition.
- [x] Verify whether Gemini and Qwen services translate system/developer style messages into provider-specific formats.
- [x] Recommend a lead-qualification message structure for greeting, discovery, qualify, callback, and closing, including direct jumps and terminal behavior.
- [x] Assess whether the UI should expose role and task messages for each node and whether greeting must be the initial node.
- [x] Assess `filter_incomplete_user_turns=True`: exact component/API, current setting, applicability, and effect.

## Functions, actions, transitions, and state

- [x] Explain the separate `change_node` tool and whether it can be replaced by tool-linked transitions.
- [x] Compare current node functions and edge functions with declarative `transition_to`, including outcome-based branch tables.
- [x] Compare current entry/exit hooks with Pipecat pre-actions and post-actions; identify brittleness when adding tools.
- [x] Assess global functions shared by all nodes.
- [x] Assess configurable fact-capture tools and call state (including callback booked and WhatsApp sent), persistence, and use after context reset.
- [x] Identify any other custom mechanisms that duplicate or bypass built-in Pipecat behavior.

## Evidence and deliverables

- [x] Answer every question with current-code paths/snippets, current Pipecat references, rationale or uncertainty about why code is that way, options, and blockers.
- [x] Separate confirmed behavior from suggestions and historical rationale that cannot be proven from code.
- [x] Record prioritized implementation plans in `plans/` without changing runtime behavior during this audit.
- [x] Run narrow verification of created docs and inspect the final diff.
