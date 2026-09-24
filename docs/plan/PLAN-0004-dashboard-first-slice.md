---
id: PLAN-0004
title: Dashboard implementation slices and live monitoring path
status: In progress
date: 2026-09-24
related: [RFC-0004, RFC-0005, RFC-0006, RFC-0013]
---

# Dashboard build sequence

Visual thesis: cool grey operator canvas, near-white work islands, restrained blue actions. Preserve reference palette, shadcn token names, sidebar density and padding. Improve form labels, grouping and available width. Tailwind utilities own visual styling.

Content plan: route orientation, current records, focused configuration form, then supporting run detail. No marketing hero or card mosaic. Interactions: sidebar collapse, tab selection, row hover and revision-aware actions. Keep animation subtle.

## Current slice: Runs first

- Auth gate with operator Bearer token in tab memory; no storage or URL token.
- Reload-safe routes for runs and future pages. Non-Runs pages are explicit placeholders.
- Previous agent and settings forms were removed from the dashboard, not from the API. They will be rebuilt in page modules against resolved contracts. Agent-version links open a read-only reference; the full editor remains pending.
- Runs list shows actual stored states, contact snapshots, filtering and direct links. Detail groups real evidence by exchange, shows overlapping provider/tool timing, transcript, tool-result consumption, saved prompt and authenticated full-call recordings.
- Vite/React Router with Tailwind CSS v4 and CLI-installed shadcn/ui Radix components. The stylesheet contains theme tokens and Tailwind directives, not component CSS.
- Direct routes for run and agent version IDs. Run lens uses URL query state. Live run polling reads stored evidence; listen-only streaming is not implemented.

## Next implementation slices

1. Restore the agent version editor and other pages in `src/pages/` with typed API contracts. The current version page is read-only.
2. Wire the real runtime to resolved provider/audio/VAD/cadence settings. Add endpoint claim fencing to the API-dispatched live call path before dashboard dial controls.
3. Wire finalized transcript, spans, flow visits, tool results and artifact registration to the live call; use safe relative paths and distinct caller/agent/mixed kinds.
4. Build live monitoring from RFC-0013: authenticated short-lived ticket, run event stream, bounded mixed-audio fanout, AudioWorklet playback and reconnect recovery.
5. Add contact and callback views, mutable knowledge management, tools, action integrations and safe modem diagnostics as their missing backend routes land.
6. Build analytics only after timing, classification and cost coverage are measured.

## Gates

- Dashboard TypeScript and production build pass.
- Run list and inspector never fabricate missing evidence or infer an exact message/tool or tool-result/LLM link from timestamps.
- No page presents planned capabilities or missing evidence as observed state.
- Audio monitor cannot block pipeline or expose operator token in socket URL.
