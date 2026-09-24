# Voice AI Dashboard — Design & Engineering Guide

This document is the canonical design system, architecture specification, and frontend engineering standard for the Voice AI dashboard. All frontend surfaces, components, layouts, and data flows must conform to these conventions.

---

## 1. Frontend Architecture & Directory Structure

The Voice AI dashboard is built as a single-page application using **React 19**, **Vite 7**, **TypeScript 5.9**, **Tailwind CSS 3/4**, and **shadcn/ui** primitives.

### 1.1 Directory Tree

```text
apps/dashboard/
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
└── src/
    ├── app/                     # App entrypoint, global providers, routing root
    │   ├── App.tsx              # App shell & router container
    │   ├── providers.tsx        # QueryClient, Auth/OperatorProvider, TooltipProvider
    │   └── router.tsx           # Route tree & navigation configuration
    ├── routes/                  # Route-level page entry points (URL mapping)
    │   ├── overview.tsx
    │   ├── agents/
    │   │   ├── index.tsx        # Agents list
    │   │   ├── detail.tsx       # Agent overview & version selector
    │   │   └── editor.tsx       # Version draft authoring & node graph
    │   ├── runs/
    │   │   ├── index.tsx        # Runs / conversations split list
    │   │   └── detail.tsx       # Turn waterfall, transcript & raw inspector
    │   ├── contacts/
    │   │   ├── index.tsx        # Contacts & leads directory
    │   │   └── detail.tsx       # Contact profile, facts & run history
    │   ├── knowledge/
    │   │   ├── index.tsx        # Knowledge bases list
    │   │   └── detail.tsx       # Sources, chunks & search tester
    │   ├── tools/
    │   │   ├── index.tsx        # Tool definitions & version history
    │   │   └── editor.tsx       # Tool JSON schema & handler editor
    │   ├── integrations/
    │   │   ├── index.tsx        # Connections (WhatsApp, Meta Cloud)
    │   │   └── detail.tsx       # Connection settings, media & secret management
    │   ├── endpoints/
    │   │   └── index.tsx        # Runtime endpoints (SIM7600, SIP) & lease monitors
    │   ├── callbacks/
    │   │   └── index.tsx        # Scheduled callbacks & dispatch queue
    │   └── settings/
    │       └── index.tsx        # Workspace retention & logging policy
    ├── features/                # Domain-specific feature modules
    │   ├── agents/              # Agent versioning, node graph editor, tool binding
    │   │   ├── components/
    │   │   ├── hooks/
    │   │   ├── types.ts
    │   │   └── utils.ts
    │   ├── runs/                # Waterfall trace, transcript sync, metrics summary
    │   │   ├── components/
    │   │   │   ├── WaterfallView.tsx
    │   │   │   ├── TranscriptView.tsx
    │   │   │   ├── TurnDetailPane.tsx
    │   │   │   ├── LatencyBreakdown.tsx
    │   │   │   ├── AudioPlayer.tsx
    │   │   │   └── RawEventDrawer.tsx
    │   │   ├── hooks/
    │   │   │   ├── useRunTimeline.ts
    │   │   │   └── useRunLiveStream.ts
    │   │   ├── types.ts
    │   │   └── utils.ts
    │   ├── contacts/            # Contact facts, callback trigger, lead status
    │   ├── knowledge/           # Ingestion status, chunk viewer, test search
    │   ├── integrations/        # Secret submission, WhatsApp template preview
    │   └── execution/           # Call launcher, manual dialer, lease recovery
    ├── components/
    │   ├── ui/                  # Raw shadcn/ui primitives (Button, Dialog, etc.)
    │   │   ├── button.tsx
    │   │   ├── dialog.tsx
    │   │   ├── dropdown-menu.tsx
    │   │   ├── input.tsx
    │   │   ├── select.tsx
    │   │   ├── sheet.tsx
    │   │   ├── table.tsx
    │   │   ├── tabs.tsx
    │   │   ├── tooltip.tsx
    │   │   └── ...
    │   └── shared/              # Reusable composite UI components
    │       ├── StatusBadge.tsx  # Run, agent, connection status indicators
    │       ├── FormattedDate.tsx# Timezone-aware timestamp renderer
    │       ├── DurationText.tsx # Millisecond / second formatter
    │       ├── LatencyBar.tsx   # Visual latency contribution bar
    │       ├── EmptyState.tsx   # Empty search/list/detail view
    │       ├── ErrorCard.tsx    # API failure banner with retry action
    │       ├── ConfirmDialog.tsx# Destructive action gate
    │       ├── JsonViewer.tsx   # Monospace collapsible syntax-highlighted JSON
    │       ├── CodeEditor.tsx   # Prompt / configuration monospace editor
    │       └── SearchInput.tsx  # Debounced URL-bound filter input
    ├── layouts/                 # Top-level shell layouts
    │   ├── AppLayout.tsx        # Main sidebar + header + breadcrumbs shell
    │   ├── SplitViewLayout.tsx  # Two-column master-detail layout (Runs, Contacts)
    │   └── FocusLayout.tsx      # Full-width distraction-free editor layout (Flow, Prompts)
    ├── api/                     # Backend API client and generated schemas
    │   ├── client.ts            # Type-safe Fetch/Ky HTTP client with Bearer auth
    │   ├── generated/           # OpenAPI types generated via openapi-typescript
    │   │   └── api.d.ts
    │   └── endpoints/           # Typed endpoint wrappers per domain
    │       ├── agents.ts
    │       ├── runs.ts
    │       ├── contacts.ts
    │       ├── knowledge.ts
    │       ├── integrations.ts
    │       └── workspace.ts
    ├── stores/                  # Transient client state (Zustand / URL store)
    │   ├── authStore.ts         # In-memory operator token (never persisted to disk)
    │   └── layoutStore.ts       # Sidebar collapsed state, panel widths
    ├── hooks/                   # Cross-cutting utility hooks
    │   ├── useDebounce.ts
    │   ├── useUrlState.ts       # Synced query parameters
    │   └── useClipboard.ts
    ├── lib/                     # Utilities and helpers
    │   ├── utils.ts             # cn (clsx + tailwind-merge)
    │   ├── formatters.ts        # ID truncation, bytes, dates, currency
    │   └── constants.ts         # Colors, default limits, status themes
    └── types/                   # Cross-cutting shared TypeScript types
        └── index.ts
```

### 1.2 Responsibilities & Separation of Concerns

1. **Pages (`routes/`)**: Pure route coordinators. They read URL parameters, invoke feature hooks, and pass data into feature view components. Pages contain minimal JSX logic.
2. **Feature Components (`features/*/components/`)**: Domain-specific UI elements. They understand entity models (e.g., an `AgentVersionTool` binding row or a `TraceSpan` latency bar) and handle user interactions for that domain.
3. **Shared Components (`components/shared/`)**: Domain-agnostic composite components used across 2+ features (e.g., `StatusBadge`, `FormattedDate`, `JsonViewer`).
4. **UI Primitives (`components/ui/`)**: Standard headless primitives styled with Tailwind (shadcn/ui). Unmodified or lightly extended to support custom variants.
5. **Server State (`api/` + `@tanstack/react-query`)**: All server state is managed via React Query hooks with structured query keys (e.g., `['runs', runId, 'timeline']`). No hand-rolled cache objects.
6. **Global State**: Kept minimal. In-memory `operator_token` and UI preferences (sidebar collapse) are stored in React Context or a tiny Zustand store. Route state (filters, active tab, selected entity) is stored strictly in the URL query string.

---

## 2. Component Conventions & shadcn/ui Usage

### 2.1 Component Composition Hierarchy

```text
┌─────────────────────────────────────────────────────────┐
│ Page Component (routes/runs/detail.tsx)                 │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ Layout Component (layouts/SplitViewLayout.tsx)      │ │
│ │ ┌─────────────────────────────────────────────────┐ │ │
│ │ │ Feature View (features/runs/WaterfallView.tsx)   │ │ │
│ │ │ ┌─────────────────────────────────────────────┐ │ │ │
│ │ │ │ Shared Component (components/LatencyBar.tsx)│ │ │ │
│ │ │ │ ┌─────────────────────────────────────────┐ │ │ │ │
│ │ │ │ │ UI Primitive (components/ui/tooltip.tsx)│ │ │ │ │
│ │ │ │ └─────────────────────────────────────────┘ │ │ │ │
│ │ │ └─────────────────────────────────────────────┘ │ │ │
│ │ └─────────────────────────────────────────────────┘ │ │
│ └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

### 2.2 Standard Patterns

- **Dialogs vs Sheets**:
  - Use **Dialogs** (`components/ui/dialog.tsx`) for modal confirmations, critical inputs, or small self-contained forms (e.g., "Launch Call", "Add Secret", "Clone Draft").
  - Use **Sheets / Drawers** (`components/ui/sheet.tsx`) for slide-out inspection panels that maintain reading context (e.g., "Raw Event Inspector", "Tool Execution JSON", "Contact Quick Facts").
- **Tables & Lists**:
  - Always use tabular numbers (`tabular-nums`) for timestamps, IDs, durations, token counts, and metrics.
  - Wrap table headers with sticky styling (`sticky top-0 bg-card z-10`).
  - Table rows must feature hover highlight (`hover:bg-muted/50`) and active selection state (`bg-primary/5 ring-1 ring-primary/20`).
- **Empty States**:
  - Never show a blank container. Use `components/shared/EmptyState.tsx` with an icon, title, description, and primary CTA button.
- **Loading & Skeleton States**:
  - Skeletons must match the exact height and layout of the rendered row or card to eliminate layout shift (CLS = 0).
- **Confirmation Flows**:
  - Destructive actions (delete knowledge base, discard draft, terminate active call, force reconcile) require an `AlertDialog` with explicit typed confirmation when high-risk.

---

## 3. Tailwind CSS & Visual Design Tokens

### 3.1 Color & Surface Hierarchy

The dashboard uses the light reference palette: cool grey canvas, near-white islands, restrained blue action and thin neutral borders. Define semantic shadcn variables in Tailwind configuration. Components use Tailwind utilities only; no handwritten component CSS or inline styles. The reference supplies visual direction, not reusable API contracts.

| Token | Class | Semantic Purpose |
| :--- | :--- | :--- |
| **Canvas** | `bg-background` (`#eef0f3`) | Root canvas |
| **Surface** | `bg-card` (`#f8f9fb`) | Sidebar and grouped work areas |
| **Raised surface** | `bg-white` | Active editor and modal |
| **Muted surface** | `bg-muted` (`#e4e7ec`) | Secondary rows |
| **Action** | `bg-primary` (`#315efb`) | Primary action and active navigation |
| **Foreground** | `text-foreground` (`#172033`) | Main content |
| **Secondary text** | `text-muted-foreground` (`#687386`) | Descriptions and timestamps |
| **Border** | `border-border` (`#d4d9e2`) | Dividers and island boundaries |

### 3.2 Spacing, Density & Typography

- **Grid & Gutters**:
  - Sidebar: `w-60` expanded (`w-14` collapsed).
  - Page Padding: `p-3 sm:p-4 lg:p-6`.
  - Content Max Widths: Uncapped for master-detail split views (`w-full`), `max-w-6xl` for focused configuration editors.
- **Typography Hierarchy**:
  - Page Titles: `text-xl sm:text-2xl font-semibold tracking-tight text-foreground`.
  - Section Headings: `text-sm font-semibold text-foreground`.
  - Body Text: `text-sm text-foreground leading-relaxed`.
  - Secondary / Captions: `text-xs text-muted-foreground`.
  - Monospace / Technical: `font-mono text-xs tabular-nums text-foreground`.

Group related fields in one island with `p-4` or `p-5` and `gap-4` or `gap-6`. Avoid a card per input. Use one primary sidebar with page-local tabs or a contextual rail. Stack editor columns when the content area narrows. Keep focus, validation, disabled and conflict states clear.

### 3.3 Status & Category Color Tokens

```typescript
export const STATUS_THEMES = {
  completed: { dot: "bg-emerald-600", badge: "bg-emerald-50 text-emerald-700" },
  running:   { dot: "bg-blue-600", badge: "bg-blue-50 text-blue-700" },
  queued:    { dot: "bg-sky-600", badge: "bg-sky-50 text-sky-700" },
  uncertain: { dot: "bg-amber-600", badge: "bg-amber-50 text-amber-800" },
  failed:    { dot: "bg-red-600", badge: "bg-red-50 text-red-700" },
  draft:     { dot: "bg-slate-500", badge: "bg-secondary text-muted-foreground" },
  published: { dot: "bg-emerald-600", badge: "bg-emerald-50 text-emerald-700" },
};
```

---

## 4. Application Shell & Navigation

```text
┌──────────────────────────────────────────────────────────────────────────┐
│ [Logo] Voice AI Control Plane   [Breadcrumbs: Runs / 43638018]  [Token]  │
├──────────────┬───────────────────────────────────────────────────────────┤
│ ❖ Overview   │                                                           │
│ ⌁ Runs       │                                                           │
│ 👤 Contacts   │                   MAIN CONTENT AREA                       │
│ 🤖 Agents     │                                                           │
│ 📖 Knowledge  │       (Master List / Split Pane / Detail Canvas)          │
│ ⚙ Tools      │                                                           │
│ 🔌 Channels   │                                                           │
│ ⏱ Callbacks  │                                                           │
│ 📡 Endpoints │                                                           │
│ ⚙ Settings   │                                                           │
├──────────────┴───────────────────────────────────────────────────────────┤
│ [🟢 SIM7600 Active: COM16/17]                  [Operator Session: Active]│
└──────────────────────────────────────────────────────────────────────────┘
```

### 4.1 Navigation Hierarchy

1. **Top Header**:
   - Application logo & service indicator (`Voice AI v0.2.0`).
   - Breadcrumbs reflecting route hierarchy (`Agents / Maya / Version 1`).
   - Quick Action: Dial New Call (`POST /api/v1/calls`).
   - Operator Token status chip (indicates active Bearer authentication from browser memory).
2. **Primary Left Sidebar**:
   - Collapsible (`w-60` to `w-14`).
   - Grouped sections:
     - **Operations**: Overview, Runs & Conversations, Scheduled Callbacks, Live Telephony.
     - **Authoring**: Agents & Flows, Prompt Templates, Tools & Catalog, Knowledge Bases.
     - **Infrastructure**: Runtime Endpoints & Modems, Channels (WhatsApp), Workspace Policy.
3. **Contextual Sub-navigation**:
   - Handled via horizontal sub-tabs or split panes within each domain page rather than adding a third sidebar level.

---

## 5. Data-Display Conventions

| Domain Concept | Display Rule | Example |
| :--- | :--- | :--- |
| **Entity ID** | Show first 8 chars uppercase with copy-to-clipboard on hover | `43638018` *(copies full UUID)* |
| **Timestamp** | Localized with timezone abbreviation | `23 Sep 2026, 21:18:36 IST` |
| **Duration** | Milliseconds `< 1s`, seconds `< 60s`, minutes + seconds for calls | `420 ms` / `14.2 s` / `4m 12s` |
| **Latency Metric** | Micro-badge with latency tag and numerical value | `TTFT: 320ms` / `TTFA: 650ms` |
| **Phone Number** | E.164 formatted with national grouping | `+91 73875 01703` |
| **Classification**| Pill badge with lead temperature & probability | `🔥 Hot (85%)` / `❄ Cold` |
| **Token Usage** | Input / Output token breakdown | `420 in / 68 out` |
| **Hardware Ports**| Port chip with status indicator | `AT: COM16 • Audio: COM17` |

---

## 6. Async, Server State & Polling Rules

1. **React Query Configuration**:
   - `staleTime: 5000` for standard lists (agents, contacts, tools).
   - `staleTime: 0` for active run timeline and active calls.
2. **Polling & Realtime Updates**:
   - Live runs in status `running` or `queued` poll `/api/v1/runs/{id}/timeline` every **1500 ms**.
   - Completed runs (`status != "running"`) immediately stop polling.
3. **Optimistic Mutations**:
   - Used for quick status toggles (e.g. enabling a connection) with automatic rollback on API failure.
4. **Draft Revision Checks**:
   - When editing drafts (`AgentVersion`, `ToolVersion`, `WorkspaceSettings`), the payload **must** include the latest `revision: number`.
   - On HTTP 409 Conflict (`Draft changed by another operator`), the UI displays a conflict resolution banner prompting the operator to reload and compare diffs.

---

## 7. Accessibility & Keyboard Navigation Standards

- **Keyboard Shortcuts**:
  - `Cmd+K` / `Ctrl+K`: Open global search & quick jump palette.
  - `J` / `K` or `ArrowUp` / `ArrowDown`: Move between conversation turns or run list items.
  - `Space` / `Enter`: Expand selected turn waterfall span or play turn audio clip.
  - `Esc`: Close inspector drawer or cancel modal.
- **Focus Management**:
  - Every interactive element has an explicit focus ring (`focus-visible:ring-2 focus-visible:ring-primary focus-visible:outline-none`).
- **Screen Reader Labels**:
  - Icon-only buttons must have `aria-label` or `<span className="sr-only">`.

---

## 8. URL and Routing Conventions

Dashboard state must survive page reloads and browser back/forward navigation.

| State Dimension | URL Representation | Example |
| :--- | :--- | :--- |
| **Selected Run** | Path parameter or query param | `/runs/43638018-5120-4962-8d94-dca2896de9ce` |
| **Inspection Lens** | `lens` query param | `/runs/43638018?lens=waterfall` or `?lens=transcript` |
| **Selected Turn/Event** | `turn` / `event` query param | `/runs/43638018?lens=waterfall&turn=3&span=span_01` |
| **Agent Version** | Route path | `/agents/maya-agent-id/versions/1` |
| **Editor Tab** | `tab` query param | `/agents/maya-agent-id/versions/1?tab=flow` |
| **Search & Filters** | `q`, `status`, `time` params | `/runs?q=deepankar&status=completed&time=24h` |

---

## 9. Design Principles

1. **Information Density over Decorative Cards**: Present rich, dense data tables with clear typography and spacing rather than nesting empty cards inside cards.
2. **Progressive Disclosure**: Make high-level conversation flow readable by default; disclose exact token payloads, raw JSON, and OTel spans upon turn click.
3. **Strict Truth in Diagnostics**: Do not synthesize or fabricate missing hardware states. If an event was dropped or timing was unrecorded, show `—` or an explicit gap warning.
4. **Zero Key Leakage**: Credentials and tokens are stored in browser memory only and write-only encrypted on the backend. Never render decrypted secrets in the DOM.
