---
id: PLAN-deferred-usage-pricing
title: Provider-neutral usage and pricing persistence and UI
status: Deferred
date: 2026-09-29
related: [RFC-0003, RFC-0004, ADR-0007, PLAN-0003, PLAN-0004]
---

# Provider-neutral usage and pricing persistence and UI

## Purpose

Persist provider-reported or clearly labeled estimated usage for each billable
provider attempt, calculate an explainable estimated cost from a versioned price
catalog, and expose coverage and totals in run detail and workspace analytics.
This is an estimate and observability feature, not billing or a promise that local
rates equal a provider invoice.

## Existing groundwork

- `TraceSpan` already persists run-owned provider/model, operation status, timing,
  token fields, audio seconds and other optional metrics. `EvidenceObserver` reads
  Pipecat usage metrics and closes spans for live LLM/STT/TTS work.
- Run detail sums available LLM tokens and shows partial or missing coverage. It
  does not calculate costs or present all provider families.
- `packages/voice_runtime/voice_runtime/execution/accounting.py` defines immutable
  provider-neutral `AttemptUsage`, `UsageMeasurement`, `PricingRule`, `CostLine` and
  summary contracts plus deterministic in-memory pricing/aggregation. Unit coverage
  exists in `tests/unit/test_accounting.py`.
- These contracts are not wired to runtime adapters, SQLAlchemy models/migrations,
  APIs, durable pricing data or dashboard cost views. Span usage metrics do not by
  themselves identify a documented billable quantity or distinguish provider-reported
  usage from a framework estimate.

## Product and accounting rules

1. **Keep each attempt distinct.** Link every usage record to its existing Run and
   `TraceSpan` operation. Retries, interrupted generations and failed requests remain
   separate attempts; never infer a retry or billable quantity from a transcript.
2. **Keep measures provider neutral.** Identify provider, model, service tier, family
   (`llm`, `stt`, `tts`, `embedding`, `realtime` or `other`), purpose (foreground,
   classifier, summarizer, background or other), attempt index and start time. Record
   arbitrary named quantities with unit/dimension, quantity and whether that measure
   is billable. Examples include input/output tokens, cached input tokens, audio
   seconds, characters, requests or provider-specific units.
3. **Preserve provenance and completeness.** Each measure carries source
   (provider/framework reported, framework/local estimate, derived or unknown) and
   completeness (final, partial, estimated, missing or unknown). Null means unknown,
   not zero. Do not sum overlapping totals, reasoning and cached-token measures as
   separate billable quantities; adapters select disjoint billable dimensions.
4. **Make prices reproducible.** A pricing rule identifies provider/model/family,
   optional tier, dimension, effective interval, source URL, retrieval/access time,
   currency, unit quantity, rate and catalog version. Calculation pins the matched
   rule and copied rate/source/version/currency on each cost line. Later catalog
   edits never silently reprice historical runs.
5. **Do not hide uncertainty.** Report priced, partial, usage missing, price missing
   and ambiguous price states. Never display missing usage or price as free. Sum
   different currencies separately; no implicit FX conversion. Label computed totals
   “estimated cost” and show usage and price coverage.
6. **Make ingestion replay safe.** Use stable attempt identity and a unique key per
   run/operation/attempt. Evidence replay must be idempotent, reject conflicting
   duplicate content, and keep cost calculation deterministic. Retain source
   provider request IDs only when safe and useful; never store credentials or raw
   authorization data.
7. **Allow explicit correction.** Corrected provider statements or reviewed price
   changes create a new calculation/correction record with actor, timestamp and
   reason. Do not mutate original raw usage or erase the original estimate.

## Proposed persistence slice

Add a migration and SQLAlchemy models after accounting contracts are reviewed against
the existing evidence schema:

- `usage_attempts`: Run FK, TraceSpan FK, stable attempt key/index, purpose/family,
  provider/model/tier, start time, status, provenance metadata, and ingestion/source
  identity. Unique constraints prevent duplicate attempt and attempt-index insertion.
- `usage_measurements`: attempt FK, dimension, unit, nullable decimal quantity,
  source, completeness and billable flag. One row per attempt/dimension/unit, with
  checks for nonnegative quantity and truthful completeness.
- `pricing_rules`: provider/model/family/tier/dimension, effective start/end,
  catalog version, source URL/accessed time, currency, unit quantity and rate. Prevent
  overlapping active rules for the same match key or surface ambiguity explicitly.
- `usage_cost_lines`: immutable calculated line linked to attempt/measurement and
  pricing rule when matched; snapshot rate, unit, amount, currency, source/version and
  calculation status. Preserve a missing-price or missing-usage line.
- Optional `accounting_adjustments` only if real provider reconciliation requires
  auditable corrections; do not add a general billing ledger preemptively.

Use decimal/numeric values for quantities that require fractions and all prices.
Avoid floating-point currency arithmetic. Keep run ownership constraints consistent
with current evidence relationships. Define deletion/retention alongside run evidence
policy, and document whether pricing catalogs are retained independently of runs.

The first version can persist prices maintained from an explicit source/catalog
snapshot. Automated scraping or an unreviewed “latest price” fetch is out of scope.
Price imports must preserve effective dates, retrieval time and source evidence.

## Runtime and API sequence

1. Add adapter-level extraction from provider/framework usage events for each supported
   LLM, STT and TTS service; then cover classifier and summarizer calls as distinct
   purposes. Add embedding and realtime adapters when those call paths expose measured
   usage. Never fabricate unavailable values.
2. Normalize each provider event into the existing accounting contracts. Map it to
   the correct observed span and stable attempt index. Distinguish operation from
   attempt, and retain provider totals without double counting component measures.
3. Extend the durable evidence delivery path with versioned accounting records, replay
   identity, validation, redaction and explicit incomplete-delivery behavior. Preserve
   bounded spool guarantees and do not block live audio for database delivery.
4. Add migrations and idempotent ingestion services. Store raw normalized usage first;
   calculate and pin cost lines using exactly one effective matching rule. Replays
   must not duplicate usage or totals.
5. Add authenticated read APIs for run accounting and filtered workspace aggregates.
   Include provider family, model, purpose, time range, status, coverage and separate
   currency totals. Do not expose provider secrets or require provider credentials in
   dashboard requests.
6. Build UI only after measured coverage is available: run detail breakdown by
   operation/attempt and dimension; workspace usage view grouped by provider/model,
   family, purpose and time; filters for incomplete/unpriced activity; and clear empty,
   partial, estimated, missing-price and multi-currency states. Keep existing token
   summary explicitly labeled as token telemetry until broader accounting lands.

## Dashboard requirements

- Run detail: observed operation count, attempt/retry count, measured quantities by
  family and dimension, estimated cost by currency, unpriced count and usage/price
  coverage. Allow drill-down to provenance, status, matched price version/source and
  individual attempt. Distinguish provider-reported from framework/local estimates.
- Workspace usage: time-window totals and breakdowns with the same coverage semantics;
  aggregate only within one currency. Allow narrowing to provider, model, family,
  purpose and run status. Avoid implying that these values are an invoice.
- Missing evidence: show “not recorded” or partial coverage. Do not backfill token,
  audio or request quantities from transcript text or call duration without an explicit,
  separately labeled estimation policy.
- Accessibility and density follow RFC-0004 and `docs/design.md`; values use tabular
  numerals and missing data remains visible.

## Delivery phases

1. Review contracts and dimensions against official provider usage semantics; define
   rounding, overlap, retry and interrupted-request behavior.
2. Implement persistence, migration, replay-safe ingestion and historical read APIs
   for the already captured usage measures.
3. Wire and validate per-provider usage extraction, then report coverage per provider
   and family. Avoid claiming complete totals until all relevant call paths are covered.
4. Add reviewed versioned pricing data and immutable cost calculations with tests for
   missing/ambiguous rules, effective boundaries, retries, duplicate delivery, partial
   usage and currencies.
5. Add run and workspace UI once API coverage/status contracts are stable.

## Acceptance criteria

- Every stored quantity traces to one provider attempt and one source classification;
  duplicate delivery does not change totals.
- Unknown and partial usage remain explicit; no missing measure becomes zero.
- Pricing selects one effective rule or records a missing/ambiguous status. Historical
  cost lines retain the original rate and catalog version after future price changes.
- Failed, interrupted and retried attempts remain separately visible and are accounted
  for only according to the provider's documented billable rules.
- Aggregates never combine currencies and never label estimates as actual charges.
- Run detail and workspace views agree with API aggregation, explain coverage, and
  expose enough provenance to audit a total.
- Provider keys stay server side; usage payloads are sanitized before durable storage.
- An opt-in provider integration test or captured fixture verifies each adapter's
  field mapping; ordinary tests use fixtures and never require live calls.

## Out of scope

Provider billing/plan administration, invoice reconciliation automation, budgets that
block calls, customer invoicing, FX conversion, tax, chargeback, and changing model
selection based on price. These require separate product and operational decisions.
