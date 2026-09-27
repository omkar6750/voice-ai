---
id: PLAN-0025
title: Token accounting and Groq live-call budget
status: Proposed
date: 2026-09-27
related: [PLAN-0020, PLAN-0016]
---

# Token accounting and Groq live-call budget

## Current gap

The run timeline already stores and displays nullable `prompt_tokens` and `completion_tokens` per span, but the available run has nulls. The native pipeline enables general metrics but does not set `PipelineParams.enable_usage_metrics=True`; the observer knows how to parse `LLMUsageMetricsData` if delivered. This is a likely source of the nulls, to verify with an actual provider response. The run UI renders span values but does not calculate per-call foreground/background totals. The prompt editor shows no token estimate. Null must remain “not recorded,” never zero.

## Live usage probe (2026-09-27)

One minimal streaming request through each provider API, using this account's configured credentials, returned:

- Groq (`qwen/qwen3.8-27b`): `usage.prompt_tokens=18`, `completion_tokens=2`, `total_tokens=20`; `x-ratelimit-*` headers were present. The API response also supplied queue and inference times.
- Gemini (`gemini-3.5-flash-lite`): `usageMetadata.promptTokenCount=6`, `candidatesTokenCount=1`, `totalTokenCount=7`, plus `promptTokensDetails`. `gemini-2.5-flash-lite` appeared in ListModels but returned 404 for this account, with a message directing new users to 3.5.

These are response-shape probes, not full Pipecat calls. Installed Pipecat 1.11 maps both responses into `LLMTokenUsage` and emits usage before `LLMFullResponseEndFrame`. The evidence contract now persists provider-reported `total_tokens` and cache counts; the dashboard totals conversation LLM spans only and labels incomplete coverage. The remaining work below is still required for a true whole-call total, including background inference, rate headers, and real-call verification. The probe script prints no credentials or generated text.

## Implementation sequence

1. Enable/verify Pipecat usage metrics and correlate each provider usage event to its exact LLM operation, including streaming/tool-call iterations and interrupted requests. Check Groq/Gemini usage semantics and fallback: if provider returns no usage, preserve null with a reason instead of estimating it as authoritative usage.
2. Extend evidence only as necessary to distinguish foreground LLM, classifier, summarizer and any retries, with input, output, reasoning and total per inference. Avoid double-counting partial/final spans and preserve model/provider identity.
3. Aggregate per run: total input/output/combined tokens by foreground/background and provider/model, per-call totals, max rolling 60-second usage, and rate-limit observations (`retry-after`, remaining/reset headers when available, redacted). Generate typed API contract from OpenAPI for dashboard; no duplicate hand-maintained DTOs.
4. Add an editor token *estimate* for system prompt, active node, tool schemas, and expected context. Label it approximate and model-dependent; do not imply a local tokenizer can equal provider billing. Show fixed prompt footprint separately from variable dialogue and output reserve. Show mock offer text and tool descriptions in that footprint.
5. Establish foreground priority when near Groq TPM: defer optional classifier/summary requests or route approved background work to another provider; bound tool results; cap max output while preserving a useful response. On 429 honor retry-after with bounded recovery speech/timeout and clear evidence, avoiding an infinite retry or silence.
6. Validate with one real browser call and one carrier call (when available), recording rate headers and provider usage; compare dashboard sums with provider response/logs.

## Tests and acceptance

- Unit tests for usage frame association, multiple calls within one exchange, streaming finalization, cancellation, null usage, reasoning tokens, and no double-counting.
- API/dashboard tests for per-operation and whole-call totals, foreground/background split, rate-limit UI and prompt estimate labeling.
- Load simulation triggers threshold/429 and verifies foreground priority plus bounded spoken fallback.

Refs: [Pipecat metrics](https://docs.pipecat.ai/pipecat/fundamentals/metrics), [Groq rate limits](https://console.groq.com/docs/rate-limits).
