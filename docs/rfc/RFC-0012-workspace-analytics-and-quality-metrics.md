---
id: RFC-0012
title: Workspace analytics, pipeline latency distributions, and quality metrics surface
status: Proposed
version: 1
date: 2026-09-23
authored_by: omkar
related: [RFC-0001, RFC-0003, RFC-0004, RFC-0006, RFC-0007]
---

# RFC-0012 · Workspace analytics, pipeline latency distributions, and quality metrics surface

## Implementation amendment, 2026-09-24

- Aggregate analytics routes need backend work. Start with reliable status counts and evidence coverage. Defer cost, conversion and percentile charts until live timing/analysis is complete.
- Define denominator and sample count for every metric. Unknown is not zero. Classifier labels are not confirmed conversions. Separate provider TTFT, TTS-first-audio and user-perceived delay.
- Date filters state viewer timezone; storage remains UTC. Unavailable cost stays null until model rate/version is known.

## 1. Context

Operational efficiency and user experience in a real-time Voice AI system depend on tracking core quality metrics across thousands of calls:
- **Pipeline Latency**: Time to First Token (TTFT), Time to First Audio (TTFA), End-of-Turn VAD silence padding.
- **Call Outcomes & Conversions**: Connection success rate, duration distribution, lead qualification rates (hot, warm, cold).
- **Execution Errors**: STT recognition failures, LLM timeouts, TTS synthesizer dropouts, and hardware disconnects.
- **Provider Costs & Token Consumption**: Prompt tokens, completion tokens, character counts for TTS, and audio minutes.

Instead of vanity metrics and empty decorative widgets, the analytics surface provides high-density operational telemetry, latency percentiles (P50, P90, P99), and drill-down links directly into affected runs.

## 2. Goals

- Provide high-density **KPI Overview Cards** (Total Calls, Connection Rate, Avg Duration, Avg TTFA, Qualified Leads).
- Present **Latency Percentile Distributions** (P50, P90, P99 for STT, LLM, TTS, and Total Turn Latency) with time-range filtering.
- Display **Lead Conversion Funnels** based on post-call classification facts (`hot`, `warm`, `cold`, `not_interested`).
- Display an **Error & Interruption Breakdown Table** with direct links into the corresponding run timeline and raw OTel trace.
- Provide date range picker (`Today`, `Last 7 Days`, `Last 30 Days`, `Custom Range`) with URL query persistence.

## 3. Non-Goals

- Ad-hoc custom SQL query builder inside the browser.
- External marketing attribution / CRM sync dashboards (delegated to external webhooks and CRM integrations).

## 4. Routes

- `/analytics` — Operational overview, KPI metrics, latency percentiles, and conversion trends.
- `/analytics/latency` — Deep-dive latency distribution charts (STT vs LLM vs TTS breakdown).
- `/analytics/errors` — Aggregated failure log grouped by error type and provider.

## 5. API Dependencies

### Consumed Existing APIs
- `GET /api/v1/runs` — Filterable run query (status, created_after, created_before, agent_id).
- `GET /api/v1/callbacks` — Status counts of completed and pending callbacks.
- `GET /api/v1/contacts` — Total contacts and lead facts aggregation.

### Required Backend / API Additions
- `GET /api/v1/analytics/overview` — Workspace-level aggregation returning total calls, connection rate, mean duration, and total token usage over a given time window.
- `GET /api/v1/analytics/latency-percentiles` — Time-series latency percentiles (P50, P90, P99) for STT, LLM TTFT, and TTS TTFA.
- `GET /api/v1/analytics/lead-conversions` — Lead temperature counts (`hot`, `warm`, `cold`, `unclassified`) grouped by agent version.
- `GET /api/v1/analytics/error-summary` — Error frequency table aggregated by error code (`stt_timeout`, `tts_dropout`, `tool_exception`, `modem_busy`).

## 6. Layout & Feature Components

### 6.1 Analytics Overview Layout
```text
┌────────────────────────────────────────────────────────────────────────┐
│ Workspace Analytics & Performance     [Agent: All ▼] [Range: 7D ▼]    │
├────────────────────────────────────────────────────────────────────────┤
│ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐   │
│ │ Total Calls  │ │ Connect Rate │ │ Avg TTFA     │ │ Hot Leads    │   │
│ │ 1,248        │ │ 94.2%        │ │ 820ms (P50)  │ │ 184 (14.7%)  │   │
│ │ +12% vs prev │ │ +1.1% vs prev│ │ -45ms vs prev│ │ +28 vs prev  │   │
│ └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘   │
├────────────────────────────────────────────────────────────────────────┤
│ Latency Distribution Breakdown (P50 / P90 / P99)                       │
│ ┌────────────────────────────────────────────────────────────────────┐ │
│ │  STT (Sarvam):            [  180ms  |  290ms  |  410ms  ]          │ │
│ │  LLM TTFT (Groq/Llama3):  [  220ms  |  380ms  |  650ms  ]          │ │
│ │  TTS TTFA (Cartesia):     [  140ms  |  210ms  |  340ms  ]          │ │
│ │  Total Turn Latency:      [  780ms  | 1120ms  | 1680ms  ]          │ │
│ └────────────────────────────────────────────────────────────────────┘ │
├────────────────────────────────────────────────────────────────────────┤
│ Top Errors & Anomalies (Last 7 Days)                                   │
│ ┌───────────────────────────┬─────────┬──────────────┬───────────────┐ │
│ │ Error Reason              │ Count   │ Impacted Runs│ Action        │ │
│ ├───────────────────────────┼─────────┼──────────────┼───────────────┤ │
│ │ SIM7600_CARRIER_BUSY      │ 14      │ 14 runs      │ [View Runs]   │ │
│ │ GROQ_RATE_LIMIT_429       │ 3       │ 3 runs       │ [View Runs]   │ │
│ │ TTS_SOCKET_DISCONNECT     │ 1       │ 1 run        │ [View Runs]   │ │
│ └───────────────────────────┴─────────┴──────────────┴───────────────┘ │
└────────────────────────────────────────────────────────────────────────┘
```

### 6.2 Key Components
- `KpiMetricCard`: Value, delta change indicator, and concise description.
- `LatencyPercentileChart`: Grouped horizontal bar chart visualizing P50, P90, and P99 latency stages for the cascaded voice pipeline.
- `LeadConversionFunnel`: Visual progress breakdown from Initiated Call -> Connected -> Engaged (>3 turns) -> Qualified Lead.
- `ErrorAggregationTable`: Sortable table with one-click drill down linking to the filtered `/runs?status=failed&error_code=...` page.
