# Handoff 004: token usage, provider metrics, pricing, and cost UI

## Objective

Design a provider-agnostic accounting model for foreground LLM calls,
classifier calls, summarizer calls, retries, interrupted generations, cached
tokens, rate limits, and estimated cost per operation and per run.

## Current implementation

Runtime evidence:

- `packages/voice_runtime/voice_runtime/execution/observer.py`
- `packages/voice_runtime/voice_runtime/execution/exchange.py`
- `packages/voice_runtime/voice_runtime/contracts/evidence.py`
- `apps/api/voice_api/schemas/timeline.py`
- `apps/api/voice_api/api/v1/endpoints/evidence.py`

The observer handles `LLMUsageMetricsData`:

```python
values["prompt_tokens"] = metric.value.prompt_tokens
values["completion_tokens"] = metric.value.completion_tokens
values["total_tokens"] = metric.value.total_tokens
```

The dashboard currently aggregates spans categorized as foreground LLM work in:

- `apps/dashboard/src/pages/runs/detail.tsx`
- `apps/dashboard/src/pages/runs/inspector.tsx`

The timeline stores nullable usage fields. Null means “not recorded”; it must
not be silently changed to zero or estimated usage.

Provider configuration/catalog code:

- `apps/api/voice_api/services/provider_registry.py`
- `apps/api/voice_api/schemas/providers.py`
- `packages/voice_runtime/voice_runtime/contracts/providers.py`

There is currently no versioned pricing registry.

## Web-research instructions

The research agent has no repository or CLI access. Search official Pipecat
documentation/source for `LLMUsageMetricsData`, `LLMTokenUsage`, streaming
metrics, tool-call loops, interruption, and summarizer usage. Search official
provider API documentation for usage metadata and rate-limit headers for Groq,
Gemini, Sarvam, Cartesia, and future provider adapters.

Search official pricing pages and model cards for pricing dimensions. Prices
change, so every pricing claim must include a source URL, effective/access
date, currency, billing unit, and model/version scope. Do not invent prices.

Determine:

1. Which usage frames are emitted for streaming responses, tool-call loops,
   interrupted responses, classifiers, and dedicated summarizer LLMs.
2. How to associate a usage metric with the exact operation when multiple LLMs
   are active or a response is interrupted.
3. Which provider headers or response metadata are useful for rate-limit
   evidence and how they should be redacted.
4. Which pricing dimensions are needed for Groq, Gemini, Sarvam, Cartesia, and
   future providers: input, output, cached input, reasoning, audio, model tier,
   currency, effective date, and billing unit.
5. How to represent authoritative provider-reported usage versus local estimates.

## Required deliverable

Provide:

- evidence/schema changes;
- provider-neutral operation categories;
- pricing registry model and versioning rules;
- aggregation queries/API response shape;
- dashboard breakdown design;
- prompt-token estimate design and labeling;
- tests for missing usage, retries, interruption, summarization, classifier
  work, cached tokens, and provider cost changes.

Do not hardcode current provider prices without a source and effective date.
Separate documented provider behavior from recommended local accounting design,
and identify which fields require runtime instrumentation rather than web
research.
