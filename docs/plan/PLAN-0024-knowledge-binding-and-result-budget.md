---
id: PLAN-0024
title: Knowledge tool binding and bounded results
status: Proposed
date: 2026-09-27
related: [PLAN-0020, RFC-0003]
---

# Knowledge tool binding and bounded results

## Decision and present behavior

The user is right: a tool bound to one KB must search only that KB's chunks. Current `native.py` query handler ignores the particular tool binding key, loops over all agent-linked KB IDs, and even falls back to all database KB IDs when none are linked. `resolution_service.py` also creates a generic auto-KB tool when knowledge exists. This is a scope correctness/privacy issue, independent of whether KB retrieval is fast. The current available run has no KB call; the older path supplied by the user was not present, so its latency cannot be attributed to retrieval from available evidence.

## Implemented safeguard (2026-09-27)

New KB-created tool versions carry `knowledge_base_id`. The live handler dispatches by registered handler identity, verifies that exact KB is attached to the agent, and searches only that base. Missing/mismatched scope fails closed; the global-DB fallback and implicit generic tool were removed. Model-visible excerpts are capped at three chunks of 600 characters each, with chunk IDs; result metadata no longer duplicates full chunk text. Unit tests cover the two-KB isolation and missing scope paths.

Existing published KB tool versions created before this field do not acquire an identity automatically and will return the explicit scoping error if invoked. Repairing them needs new correctly scoped tool versions and rebinding a draft agent; do not silently mutate immutable published tool definitions or infer identity from a name. Retrieval latency measurement and live KB benchmarking remain open, but the operator currently prefers not to use KB calls during live calls.

## Implementation sequence

1. Define explicit KB identity in the resolved tool binding: one KB per tool, or an explicit multi-KB set only when the operator deliberately chooses it. At publication/resolution, validate IDs belong to the agent's attached KBs and are present; pin identity while content stays mutable per RFC-0003. Remove the implicit “search every DB KB” fallback.
2. Pass the invoked binding key/validated KB identity into the native handler; never infer scope from a tool name substring. If unbound, return a concise error and record diagnostic without data from other KBs.
3. Decide what to do with the auto-generated generic tool: either make it explicitly multi-KB with UI label/consent or disable it when single-KB binding is expected. Do not silently expand a single-KB tool to all attached KBs.
4. Bound the model-visible result to ranked citations/excerpts with max hits, chars/tokens and a short source/score. The current response duplicates text in `context` and `results`; avoid sending both full representations to the next LLM. Keep richer retrieval evidence outside LLM context.
5. Measure embedding, database query, rerank/merge, tool wall time, result bytes/tokens, and next LLM latency. Compare no-KB vs one-KB on the same question before deciding whether to use live KB. Preserve the user's current preference to keep sufficient stable facts in node prompts and not invoke KB during calls.

## Tests and acceptance

- Two-KB isolation fixtures: a tool bound to A never returns B, even when B scores higher; no attachment means no global fallback; invalid/deleted KB fails closed; explicit multi-KB tool searches only declared IDs.
- Result truncation preserves useful citation IDs and does not break JSON/function-call pairs. Tests assert max model-visible size and retrieval evidence remains detailed.
- Latency benchmark reports stages rather than a single opaque duration. No claim that KB is “fixed” without a real call if the user later chooses to test it.

Ref: [Pipecat function calling](https://docs.pipecat.ai/pipecat/learn/function-calling).
