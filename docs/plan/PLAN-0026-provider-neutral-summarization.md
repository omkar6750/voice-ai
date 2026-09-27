---
id: PLAN-0026
title: Provider-selectable background context summarization
status: Proposed
date: 2026-09-27
related: [PLAN-0022, PLAN-0025]
---

# Provider-selectable background context summarization

## Decision and sequencing

The summarizer uses the same selectable Groq/Gemini provider catalog and LLM parameters as the conversation model. Gemini is a useful default when Groq TPM is constrained, but must not be hard-coded. A summary request on Groq shares its foreground TPM budget. “Background” does not mean the summary will always be ready for the next request. A summary must not overwrite newer conversation or active node instructions when it arrives. RESET replaces the whole LLM message list, as verified by `test_context_reset_semantics.py`. Installed Pipecat 1.11's dedicated-LLM path runs asynchronously, but its result validation checks only index and remaining message count; it does not verify the source-prefix identity or active node. Therefore do not enable this native path on the current RESET-based agent until a guarded merge is tested. Keep `RESET_WITH_SUMMARY` out of new work because Pipecat marks it deprecated.

## Implementation sequence

1. Use the already-saved `SummarizerConfig.model: LLMConfig` for either supported LLM provider, with the provider catalog, model, temperature, max tokens, top-p and provider-constrained reasoning shown in the dashboard. Build the dedicated LLM from the same validated settings path as the conversation LLM, using its own credentials. Pipecat's dedicated-LLM task does not block foreground inference. Its current result-application guard is insufficient after RESET, so add an application-level snapshot-prefix/node-generation guard or wait for an upstream fix, with race tests, before enabling it. Do not implement a second ad hoc context store.
2. Add a threshold using *measured* input tokens from completed foreground inference, with a conservative estimate fallback only when usage is unavailable. Expose start threshold, target budget, minimum retained exchanges and cooldown; enforce one in-flight summary per run. Avoid a fixed “2–3 messages” if that would split a user/assistant/tool-call pair; retain 2–3 complete recent exchanges instead.
3. Capture a context generation/version and snapshot boundary when requesting a summary. When it returns, merge only if the source prefix is still valid; retain all turns/tool results added after that boundary and the current node task/system instruction. If the active node changed, either rebase deterministically or discard/retry; never let an old summary replace a new node prompt. Missing/failed/late summary leaves current context intact.
4. Use a compact summary schema containing only durable e-commerce needs, objections, offers actually stated, commitments, callback/booking status, and opt-out. Do not add unsupported facts, secrets, or verbose transcript. Keep authoritative facts in Flow state; summary is lossy conversational memory, not a booking ledger.
5. Evaluate optional node-entry trigger only after threshold behavior works. Node-exit summarization is not a free cleanup step: it can stall transitions or race next inference. If offered, make it an explicit “request summary in background on entry” setting with strict token threshold, dedupe, and source boundary; do not add generic entry/exit actions merely for this.
6. Display summary operation, provider, token cost, age, source/target message counts, applied/discarded state, and next consuming LLM in run evidence. Keep prompt editor/operator copy honest about when compaction becomes effective.

## Tests and acceptance

- Deterministic tests for summary finishing before/after next LLM, during a node transition, during tool-call pairs, after barge-in, on Groq/Gemini 429/timeouts, and when context was reset. Assert no lost recent exchange and no stale node instruction.
- Integration test proves summary is present in a subsequent exact LLM request, not merely generated; foreground voice continues during slow Gemini response.
- Token/load test demonstrates lower Groq input-token growth without compromising factual callback/price continuity.

Ref: [Pipecat context summarization](https://docs.pipecat.ai/pipecat/fundamentals/context-summarization).
