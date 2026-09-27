---
id: PLAN-0021
title: E-commerce agent prompts and tool-reference compilation
status: Proposed
date: 2026-09-27
related: [PLAN-0020, PLAN-0018]
---

# E-commerce agent prompts and tool-reference compilation

## Decisions and scope

The internship objective is specifically e-commerce services, so the prior advice to start by discovering an arbitrary software project was wrong. Keep the caller's actual *e-commerce* need open (new store, migration, conversion, integrations, etc.). This is an assignment scenario; the $8k–$15k range, 3–4 week estimate, and discount are mock facts, not production claims. Do not change the live assignment agent in this planning slice. Keep `config.greeting` empty and use only the greeting node's LLM-generated opening until the user tests verbatim separately. No change to classifier work.

## Implementation sequence

1. Export/clone the immutable published Elevated Box agent into a draft. Capture existing prompts, tool bindings, transitions, `respond_immediately`, and test transcript snapshots; never edit the published version in place.
2. Align global system prompt and each node with an e-commerce sales scope. State the assignment-only offer data once, preferably as versioned approved mock offer facts; avoid repeating it in every node. Make the greeting ask permission to discuss the e-commerce ad, then discover the particular store/project requirement.
3. Fix `clossing` → `closing` in hot_pricing and check every transition target against the graph. Retain mock pricing only in the assignment draft, label it clearly in authoring UI, and require real offer approval before carrier production use.
4. In callback_scheduling, specify order: collect preferred time/timezone → check real availability → confirm exact slot → book only once → read confirmation. On unavailable/failed booking, offer alternatives or `schedule_callback` fallback; never claim a booking from a failed tool. Explicitly call `change_node` with `{"node":"closing"}` after a confirmed booking or when a callback is finalized, not after a failed booking. Keep it one node until test evidence shows repeated mistakes.
5. Rewrite diplomatic_exit as a one-turn terminal message: apologize if appropriate and thank the caller for their time. If a WhatsApp catalog follow-up is part of the assignment, send the approved template without asking another question, then give a concise truthful acknowledgement. Challenge: unconditional messaging must not override an explicit opt-out/stop request or a failed/unavailable send; for any real campaign, validate consent/approved-template and local messaging requirements first. Do not say “sent” before the tool confirms it.
6. Preserve `#tool_name` as an editor reference syntax. Inspect current `PromptEditor.tsx` highlighting and binding checks; compile recognized references at the backend snapshot boundary into plain actual function names/argument guidance before Pipecat context delivery. Remove only the reference marker, not literal Markdown headings or unrelated `#` text. Validate references against *node-local* exposed tool bindings and allowed transition targets at save/publish; reject unresolved references rather than silently dropping them. Show a rendered-prompt preview to the operator.
7. For each node, keep objective, one immediate conversational move, permitted tool conditions and argument shape, and failure rule concise. Do not add unbound tool names or instructions to call a tool unavailable in that node. Use fixtures for greeting, pricing, callback success/failure, diplomatic exit, closing, and caller interruption.

## Tests and acceptance

- Editor tokenizer/compilation tests for `#change_node`, punctuation/parentheses, escaped/literal `#`, unbound tools, wrong node bindings, unknown transitions, and placeholders.
- Snapshot/e2e test proves stored source prompt retains the editor marker while the sanitized Pipecat LLM request sees `change_node` without `#`; published config remains immutable.
- Scenario tests prove the opening is LLM-generated when greeting is empty; e-commerce questions stay in scope; mock price and discount remain assignment-only; callback transitions to closing only on confirmed outcome; diplomatic exit sends at most once, never on opt-out or failed send, and finishes without waiting for a reply.
- Manual call test verifies spoken acknowledgement and terminal behavior, separately from the end-call lifecycle work in PLAN-0023.

Refs: [Pipecat Flows nodes/messages](https://docs.pipecat.ai/pipecat/flows/nodes-and-messages), [functions](https://docs.pipecat.ai/pipecat/flows/functions).
