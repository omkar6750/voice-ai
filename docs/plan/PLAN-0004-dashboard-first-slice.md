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

## Built in first slice

- Auth gate with operator Bearer token in tab memory; no storage or URL token.
- Reload-safe routes for overview, agents, agent version editor, runs, run detail and workspace settings.
- Agent draft form for prompts, flow nodes, providers, audio/VAD, analysis, knowledge selection and logging. Revision-checked save, publish, clone and activate. Published versions are read-only.
- Workspace settings form and run transcript/operation inspection against current API responses.
- Shared Tailwind design tokens and controls; stylesheet has Tailwind directives only.

## Next implementation slices

1. Tighten API contracts: typed response models, provider capability/availability catalog, paginated lists. Generated frontend types then replace the current narrow local response types.
2. Wire the real runtime to resolved provider/audio/VAD/cadence settings. Add endpoint claim fencing to the API-dispatched live call path before dashboard dial controls.
3. Wire finalized transcript, spans, flow visits, tool results and artifact registration to the live call; use safe relative paths and distinct caller/agent/mixed kinds.
4. Build live monitoring from RFC-0013: authenticated short-lived ticket, run event stream, bounded mixed-audio fanout, AudioWorklet playback and reconnect recovery.
5. Add contact and callback views, mutable knowledge management, tools, action integrations and safe modem diagnostics as their missing backend routes land.
6. Build analytics only after timing, classification and cost coverage are measured.

## Gates

- New-agent minimal config validates through AgentConfig.
- Dashboard TypeScript and production build pass.
- A published agent's editor cannot mutate it; save conflict keeps local draft.
- No page presents planned capabilities or missing evidence as observed state.
- Audio monitor cannot block pipeline or expose operator token in socket URL.
