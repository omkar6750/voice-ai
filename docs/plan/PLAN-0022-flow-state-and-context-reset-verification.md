---
id: PLAN-0022
title: Flow state and context reset verification
status: Proposed
date: 2026-09-27
related: [PLAN-0020, PLAN-0019]
---

# Flow state and context reset verification

Implementation hold: the user requested a separate discussion before introducing new flow-state facts or additional variables. Only read-only RESET investigation and tests may proceed now; steps 4–6 below are proposals, not current implementation authorization.

## Verified boundary and challenge

Pipecat `flow_manager.state` is an application dictionary, not an LLM memory that populates itself. The LLM can request a tool, but a trusted handler must validate and write a fact. For this agent, don't add a generic “save every fact” tool that inflates every prompt and tool cycle. Save only consequential confirmed facts as side effects of existing handlers (e.g. successful booking/callback), and optionally capture a minimal typed fact in an existing transition's validated arguments when a later node needs it. A summary is better for diffuse conversational detail. State survives a context reset; transient dialogue does not necessarily do so.

The installed Pipecat 1.11.0 `FlowManager._update_context` selects `LLMMessagesUpdateFrame` for `RESET`; the aggregator's `_handle_llm_messages_update` calls `set_messages`, which replaces the full list. Therefore `RESET` clears prior user/assistant messages in LLM context as well as prior node task messages. An isolated regression test using the installed FlowManager now confirms APPEND vs RESET; the dashboard description has been corrected. A separate transcript/evidence record can still retain turns. The current run spool shows APPEND-like behavior: the first five LLM operations carry 2, 4, 7, 9, and 13 messages, retaining earlier user/assistant/tool content across transitions. It cannot prove what happened in a RESET run or whether today's edited draft differs from that run's published snapshot. The user-provided older `C:\Users\Omkar\dev\github\voice-api\data` path was absent. The concurrent PLAN-0019 text claiming RESET retains history must be reconciled by its owner; do not edit that agent's files during this planning task.

## Implementation sequence

1. Obtain an actual RESET run if available and compare sanitized per-LLM request message-role/content hashes immediately before and after a transition, separately from transcript persistence. Redact caller data. If no historical run exists, execute an isolated deterministic installed-Pipecat test using the repo's context aggregator and `FlowManager` (no external call).
2. Add a contract test for APPEND vs RESET: previous user/assistant/tool pairs retained by APPEND, removed by RESET, while `role_message`/system instruction and newly injected node task are handled exactly as installed version dictates. Test classifier result delivery only through coordination with its owner.
3. Fix dashboard copy and any plan/ADR wording that says “only old task prompts are replaced.” Offer a warning when RESET is chosen and a preview of what the next LLM actually sees. Do not automatically flip all existing published nodes; migration requires an explicit new version and operator review.
4. Define a small typed session-state schema for confirmed booking ID/time, callback status, opt-out, and only the e-commerce facts needed across nodes. Initialize contact/time facts before `flow.initialize`; update after successful trusted tool results. Do not persist uncertain or failed outcomes as confirmed.
5. Render known state placeholders at node entry; validate missing keys and PII exposure. Test transition arguments if used: concise schema and no extra standalone LLM call. Instrument fact-write evidence separately from tool-result prose.
6. For the Elevated Box draft, prefer APPEND until bounded summarization exists when discovery details must survive transitions. Use RESET only for deliberate independent phases or when a canonical state/summary carries all necessary facts. Test price/callback references after each transition.

## Tests and acceptance

- Offline frame-level tests assert actual LLM messages and separate transcript durability, not merely UI label semantics.
- State tests cover successful booking, failed booking, duplicate tool invocation, opt-out, callback time/timezone, and missing placeholder.
- Regression test proves no extra “save state” tool call is needed for confirmed handler results and no accidental PII appears in prompts.

Refs: [Pipecat context strategies](https://docs.pipecat.ai/pipecat/flows/context-strategies), [state management](https://docs.pipecat.ai/pipecat/flows/state-management).
