---
id: PLAN-0028
title: Effective configuration audit and language-switch deferral
status: Proposed
date: 2026-09-27
related: [PLAN-0020, ADR-0006]
---

# Effective configuration audit and language-switch deferral

## Decision

Skip automatic STT/TTS language switching now. Remove the misleading inactive `follow_caller_language` and `persist_requested_language` fields from the active contract, dashboard, and every `agent_versions.config` JSONB value, including published versions. Do not add read/write compatibility aliases or leave these fields in active agent configuration. This is an explicit cleanup exception to published-version immutability, so document it in the migration and verify all version rows. Preserve `runs.resolved_config` as historical evidence of what an earlier call actually used; rewriting a run snapshot would falsify its configuration hash. Retain static provider `tts.language` and any genuinely effective language/default fields. The more important immediate language-quality issue is prompt behavior and actual output evaluation, not dynamic service settings.

## Implementation sequence

## Confirmed effective-config audit (2026-09-27)

| Saved setting | Current live effect | Operator treatment |
| --- | --- | --- |
| `call_limits.interruptions_enabled`, `idle_timeout_secs` | Passed to Pipecat user-turn strategies; idle reprompt/call end has a focused test | Effective, pending carrier verification |
| `context.prune_node_ids`, `remove_transition_tool_pairs` | No live runtime reference | Marked planned in Context editor; do not claim pruning occurs |
| `context.summarizer.*` | Validated/stored but not applied by live host | Marked preparatory; provider/model choices now use the same catalog as conversation LLM |
| `flow.prompt_composition` | No live runtime reference | Needs dashboard label/validation review before claiming effect |
| Flow node `entry_actions`/`exit_actions` | Explicitly rejected by runtime | Keep rejection until PLAN-0023 defines semantics |
| `background_hooks` | Saved, no live action dispatch | Mark pending; do not claim effects |
| `tts.pace` for Cartesia | Explicitly rejected unless 1.0; `cartesia.generation_config` used | Provider-specific controls are effective |
| `language.follow_caller_language`, `persist_requested_language` | Removed from contract and version JSONB in migration 0024 | No operator controls; historical run snapshots unchanged |

Classifier fields are deliberately excluded from this audit while a concurrent agent owns that work. The remaining fields need the table-driven verification in step 1 below; this matrix is not a claim that the entire contract has been audited.

1. Inventory every persisted `AgentConfig`, provider, flow, context, call-limit, classifier, retrieval, logging and dashboard setting. Build a matrix: serialized/defaulted → validated → resolved → used by live runtime → exposed in dashboard → tested. Mark each effective, explicitly rejected, planned/deferred, or dead. Avoid touching concurrent classifier implementation; ask its owner to review its row.
2. Confirm known candidates: `language.follow_caller_language`, `language.persist_requested_language`, `context.prune_node_ids`, `context.remove_transition_tool_pairs`, saved summarizer fields, `flow.prompt_composition`, `call_limits.idle_timeout_secs`, `call_limits.interruptions_enabled`, generic `entry_actions`/`exit_actions`, `background_hooks`, Cartesia `pace`. Recheck each against current branch because another agent is editing runtime. Not all should be deleted: PLAN-0027 wires call limits, PLAN-0026 wires summarizer, PLAN-0023 may support actions, and unsupported declarations may need rejection rather than silent ignore.
3. For inactive automatic language switches, remove dashboard inputs, TypeScript fields, and strict Pydantic fields. Add one reviewed data migration that deletes both keys from all `agent_versions.config` language objects in one transaction, including published versions; briefly disable and restore the DB immutability guard exactly as needed. Do not add a legacy parser or compatibility fields. Leave `runs.resolved_config` historical evidence unchanged and verify its recorded hash remains valid. Re-export OpenAPI/typed client contracts if the schema includes these fields.
4. Audit prompt instructions about language: do not announce a language switch or mix grammar unnecessarily; evaluate LLM text separately from Sarvam TTS. No runtime STT/TTS update frames in this slice.
5. Add an “effective in live calls” status for operator controls, and validation that blocks save/publish of unsupported configurations that would otherwise fail only at call start. Leave draft controls visibly pending if required for future authoring, but never label no-op settings as live.

## Tests and acceptance

- Contract tests reject the removed fields in new agent configuration. Migration tests verify every agent-version row (draft and published) has the keys removed, strict parsing works, and run snapshots/evidence hashes are not rewritten.
- Table-driven audit test or explicit assertions cover each dashboard-editable field and its live runtime effect/rejection, including provider-specific fields. API/client generation and dashboard build pass.
- Manual browser/demo comparison confirms static language still works and removed switches are no longer shown as effective; no automatic language changes are introduced.

Ref: [Pipecat runtime service settings](https://docs.pipecat.ai/pipecat/fundamentals/service-settings).
