---
id: RFC-0004
title: Voice AI dashboard architecture, shell, and routing
status: Proposed
version: 1
date: 2026-09-23
authored_by: omkar
related: [RFC-0001, RFC-0003]
---

# RFC-0004 · Voice AI dashboard architecture, shell, and routing

## Implementation amendment, 2026-09-24

- Implemented dashboard uses Tailwind CSS v4 through the Vite plugin and shadcn/ui Radix components installed through the CLI. Required semantic theme variables live in the Tailwind stylesheet; styling of views remains in utilities. This supersedes the earlier "directives only" wording below.
- React Router includes `/agents/:agentId`, `/agents/:agentId/versions/:versionId?tab=...`, and `/runs/:runId`. Run detail links to its pinned agent version.

- Use light reference palette and semantic shadcn tokens from docs/design.md. Components use Tailwind utilities, no handwritten CSS or inline styles. Preserve visual character; improve form hierarchy.
- Routes survive reload and back/forward. Bearer token stays in memory, so reload requires re-entry. No token in URL or browser storage.
- Overview metrics, endpoint/callback lists and global search need backend routes. Do not show fabricated counts. Quick dial requires server-side endpoint claiming.
- Open a live monitor connection only for a selected active run; see RFC-0013.

## Implementation amendment, 2026-09-24

- The shared shell uses the light reference palette and semantic shadcn tokens in `docs/design.md`. Tailwind utilities render all components; the stylesheet contains Tailwind directives only. Form layout may differ from the reference where readability improves.
- Route state must survive reload and back/forward. Keep the operator Bearer token in memory. Re-entry after reload is expected. Never put token in URL, local storage or session storage.
- Build navigation from capabilities that exist. `GET /api/v1/overview/metrics`, endpoint lists, callback lists and global search are backend work, not existing APIs. Show no fake health or counts. The first shell can use agent and run lists; placeholders must say why data is unavailable.
- A call launch action requires server-side endpoint claim and safe dispatch. Disabling a button alone does not prevent duplicate dials.
- Live monitoring is specified in RFC-0013. Initial shell must not open a persistent monitor connection until the user opens a live run.

## 1. Context

The Voice AI platform requires a production-grade, high-density web control plane to manage autonomous voice agents, inspect live cellular calls and browser sessions, review turn-by-turn waterfalls and latency metrics, manage contacts and knowledge bases, and control action integrations.

The dashboard connects to the FastAPI backend over standardized `/api/v1` REST routes with in-memory Bearer token authentication.

## 2. Goals

- Define the top-level application shell, navigation tree, layout primitives, and responsive container hierarchy.
- Establish an in-memory operator authentication lifecycle ensuring zero credential persistence to disk or unencrypted browser storage.
- Provide global keyboard shortcuts (`Cmd+K` / `Ctrl+K`), live service status badges, breadcrumbs, and quick-action call dialing.
- Specify the complete URL scheme ensuring shareable, reload-safe dashboard state.

## 3. Non-Goals

- User multi-tenancy or external OAuth sign-in flows (the single-workspace model uses an operator token).
- Custom CSS framework implementations (strictly uses Tailwind CSS and shadcn/ui).
- In-browser persistent database storage (IndexDB/localStorage for sensitive credentials).

## 4. Routes & Navigation Architecture

```text
/                              -> Overview & System Health
/runs                          -> Master-Detail Runs & Conversations List
/runs/:runId                   -> Run Detail (Waterfall, Transcript, Inspector)
/agents                        -> Agent Catalog & Active Version Overview
/agents/:agentId/versions/:ver -> Version Draft Editor (Prompts, Flow Graph, Tools)
/contacts                      -> Contacts & Leads Directory
/contacts/:contactId           -> Contact Profile, Conversation History & Facts
/knowledge                     -> Knowledge Bases List
/knowledge/:baseId             -> Document Sources, Chunk Inspector & Search Test
/tools                         -> Tool Definitions & Published Versions
/tools/:toolId/versions/:ver   -> Tool Schema & Handler Editor
/integrations                  -> Action Integrations (WhatsApp, Meta Cloud)
/integrations/:connId          -> Connection Configuration, Media & Secret Vault
/callbacks                     -> Scheduled Callbacks & Dispatch Queue
/endpoints                     -> Runtime Hardware Endpoints (SIM7600, SIP) & Leases
/settings                      -> Workspace Retention, Logging & Callback Policy
```

## 5. API Dependencies

### Consumed Existing APIs
- `GET /api/v1/workspace` — Workspace settings & retention policy.
- `GET /api/v1/providers` — Active provider & model catalog.
- `GET /api/v1/config-schema` — JSON schemas for agent, tool, and workspace validation.
- `GET /health` — Control plane health probe.

### Required Backend Additions
- `GET /api/v1/overview/metrics` — Aggregate summary counts (total runs today, connection success rate, active endpoints, pending callbacks).

## 6. Layout & Visual Structure

### 6.1 Layout Shell (`AppLayout.tsx`)
1. **Collapsible Sidebar (`w-60` / `w-14`)**:
   - Navigation links with icon + label + keyboard indicator.
   - Live hardware status chip (e.g., `🟢 SIM7600 Active: COM16`).
   - Operator token management button with modal trigger.
2. **Top Header Bar (`h-12`)**:
   - Dynamic Breadcrumbs (`Runs / 43638018 / Waterfall`).
   - Quick "Dial Lead" CTA button opening the `LaunchCallDialog`.
   - Global search trigger (`Ctrl+K`).
3. **Main Content Canvas**:
   - Supports `SplitViewLayout` (master list on left, detail canvas on right) or `FocusLayout` (full-width flow graph and prompt editors).

## 7. Authentication & Token Management

- The operator token (`VOICE_OPERATOR_TOKEN`) is entered into a lightweight `AuthGate` dialog on initial visit.
- Stored **strictly in browser memory (React state / Zustand store)** for the duration of the browser tab session.
- Sent automatically in the `Authorization: Bearer <token>` header by the API client.
- Zero local storage or cookie serialization to prevent credential extraction.

## 8. Open Questions & Iteration Notes

1. *Hardware Webhook vs Polling*: Should the shell establish a lightweight SSE/WebSocket channel for instant hardware disconnect alerts, or is 2-second polling of endpoint status sufficient? (Initial implementation will use resilient polling).
