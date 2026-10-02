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

## Attached runtime review and implementation

- [x] Preserve the pasted implementation review verbatim in `references/attached-implementation-review.txt`.
- [x] Verify review findings against current code; see `plans/02-runtime-evidence-findings.md` for finding-by-finding disposition.
- [x] Fix WhatsApp connection consistency, runtime error attribution, and LLM-only first-token average findings.
- [x] Normalize STT/TTS provider labels from configured provider IDs.
- [x] Add applicable Pipecat metrics and TTFS evidence with units and span category.
- [x] Persist Pipecat error category and processor usability state safely.
- [ ] Investigate and implement voicemail detection before outbound agent speech. The installed Pipecat package lacks `VoicemailDetector`; hold integration pending a real dependency/API.
- [x] Make idle reprompt text/retry count configurable with existing defaults.
- [ ] Verify standard pipeline transcript event usage against call-level event semantics.
- [x] Reconcile runtime plan/memory status and improve run inspector evidence grouping.
- [x] Preserve browser/SIM7600/Twilio lifecycle and evidence ownership; no live-call tests run.
- [x] Run targeted tests/lint and record provider/hardware limitations.

## Pipecat feature implementation

- [x] Create new worktree from `main` and copy dirty/untracked starting work.
- [x] Preserve attached implementation review verbatim.
- [x] Use node `role_message`, native task message fields, `pre_actions`/`post_actions`, TTS say action, registry-backed function actions, global functions, and fact slots.
- [x] Compile each saved graph to validated Pipecat `FlowConfig` and `Flow` before constructing the runner.
- [x] Replace generic destination-valued `change_node` advertisement with native `go_to_<node>` transitions.
- [x] Add configured per-tool `transition_to` and branch table routing, retaining strict registry schemas.
- [x] Add opt-in `filter_incomplete_user_turns` default false via Pipecat's current strategy API.
- [x] Expose role/task messages, branch transitions, global functions, facts, node ordering and initial node in dashboard forms.
- [x] Regenerate OpenAPI/dashboard types in the managed worktree after the main merge.
- [x] Verify runtime unit tests, Ruff, fresh PostgreSQL migrations through `0043_remote_artifact_guard`, API health, and dashboard production build.
- [x] Merge the current local `main` commit into this worktree without changing the `main` checkout.
- [x] Fix clean-database migration bootstrap: leave the legacy tenant map empty only when there are no users, organizations, platform admins, or existing tenant rows; continue to reject unowned legacy customer data.
