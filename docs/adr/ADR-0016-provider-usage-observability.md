# ADR-0016 · Removed provider usage observability experiment

Status: Superseded / removed  
Date: 2026-09-27  
Related: [PLAN-0016](../plan/PLAN-0016-provider-usage-and-credits.md),
[ADR-0007](ADR-0007-exchanges-and-integration-secrets.md),
[ADR-0013](ADR-0013-runtime-diagnostic-model.md),
[ADR-0015](ADR-0015-provider-model-capabilities.md)

## Context

This ADR records a removed experiment. It is retained for architectural
history, but its API, service, schema, tests, and dashboard page have been
deleted because the configured providers do not expose the account usage and
credit metrics required by the feature.

The decision and implementation details below are historical; they are not
active repository contracts.

The runtime already records local usage metrics in finalized evidence spans,
but the control plane had no way to distinguish those measurements from an
account's provider quota or credits. Provider APIs also differ significantly:
some expose usage, some expose only per-request metrics, and some expose no
account usage API for the configured credential.

The user needs a provider usage view that is useful without making a false
claim such as `provider credits remaining = account credits - local usage`.

## Decision

Introduce one typed usage response with explicit state and provenance. Every
metric carries its provider, measurement, units, window, source, and checked
time. `limit` and `remaining` are nullable and remain null unless the provider
authoritatively returns them.

```text
UsageResponse
├── providers[]
│   └── ProviderUsageStatus
│       ├── state: available | unsupported | unavailable | unconfigured | error
│       └── metrics: UsageSnapshot[]  # provider_api
└── local[]
    └── UsageSnapshot                 # local_evidence
```

Provider statuses are not collapsed into a generic pipeline error. The
dashboard can therefore distinguish a missing key, an unsupported provider
usage API, a temporary outage, and an authentication failure.

## Provider adapter boundary

Provider-specific HTTP logic lives in `usage_service.py`; it receives server
settings and returns sanitized Pydantic values. The only account adapter in
this slice is Groq's Prometheus usage endpoint, which Groq documents as an
enterprise feature at [Groq Prometheus Metrics](https://console.groq.com/docs/prometheus-metrics).
The adapter reports documented `rate5m` request/token series and does not
invent account limits or credit balances.

Gemini, Sarvam, and Cartesia are represented as `unsupported` when configured.
This is deliberate: the UI shows the missing capability instead of scraping a
console or deriving a balance from local spans.

## Local evidence data flow

```text
TraceSpan rows
    │
    ├── request counts by provider/category
    ├── prompt/completion/reasoning tokens
    ├── STT/TTS audio seconds
    └── measured TTS output characters
            │
            ▼
      UsageSnapshot(source=local_evidence, window=all_time)
```

Only non-null finalized span measurements are aggregated. Local values are
shown in a separate dashboard section and are never presented as provider
quota or remaining credits.

## API and frontend behavior

`GET /api/v1/usage` is operator-protected and returns the typed
`UsageResponse`. The standard contract path remains:

```text
Pydantic schemas → FastAPI response model → OpenAPI export
→ generated TypeScript → typed Usage page
```

The dashboard adds a Usage navigation item and renders provider cards with
status badges, measured metrics, limits, remaining values, windows, and clear
messages when data is unavailable. It also renders local evidence totals and
states that those totals are not account credits.

Provider keys never leave the server. Error messages are fixed safe messages;
provider response bodies are not persisted or returned.

## Verification

- Usage adapter tests: 5 passed.
- Full backend suite: 113 passed, 31 skipped.
- Ruff passed.
- OpenAPI export and dashboard type generation passed.
- Dashboard TypeScript/production build passed.
- No database migration was necessary.

Existing unrelated warnings remain: Pipecat deprecations, two mock coroutine
warnings, and the previously documented Alembic baseline drift.

## Known limitations

- Groq usage metrics require provider account access to the documented
  enterprise endpoint; normal keys may correctly appear as unsupported.
- Provider limits, reset times, and credit balances remain `Not exposed` when
  the provider does not return authoritative values.
- Local usage is currently all-time rather than date-filtered.
