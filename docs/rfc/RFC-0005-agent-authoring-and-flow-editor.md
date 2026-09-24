---
id: RFC-0005
title: Agent authoring, versioned configuration, and flow editor surface
status: Proposed
version: 1
date: 2026-09-23
authored_by: omkar
related: [RFC-0001, RFC-0003, RFC-0004]
---

# RFC-0005 · Agent authoring, versioned configuration, and flow editor surface

## Implementation amendment, 2026-09-24

- Start with forms and a node list; graph is derived preview. Separate Prompts, Flow, Models & voice, Audio & turn-taking, Context & analysis, Tools, Knowledge, Call limits & logging.
- Save, publish and activate are distinct. Save uses revision; 409 preserves unsaved edits and shows conflict. Published versions are read-only; clone creates draft.
- Current live demo bridge applies node prompts, bindings, initial node, duration and system prompt. Other persisted provider, VAD, audio and cadence settings are not proven active. Mark these controls pending runtime connection until call tests verify them.
- Provider catalog lists models but does not report credential availability or exact supported fields. Tool controls bind exact published versions; node controls select binding keys.

## Implementation amendment, 2026-09-24

- Start with forms and a node list; graph is a derived preview. Keep one clear working column and contextual node inspector. No card per field.
- Separate tabs: Prompts; Flow; Models & voice; Audio & turn-taking; Context & analysis; Tools; Knowledge; Call limits & logging. Prompt composition (`node_only` / `global_plus_node`) is explicit.
- Save, publish and activate are distinct. Save sends the current revision; on 409 show the conflict and preserve unsaved edits. Published versions are read-only; clone creates a draft. Navigation warns about unsaved changes.
- Provider catalog currently lists models, but does not report key availability or per-field capabilities. Do not imply a model can run solely because it appears in the catalog.
- Current live demo bridge applies flow node prompts, node bindings, initial node, duration and system prompt from the resolved config. Other persisted provider, VAD, audio and cadence fields are not yet proven active in that call path. Mark these controls as configured but pending runtime connection until acceptance tests show they affect a call.
- Tool bindings are exact version pins on the agent version. Node controls choose binding keys. Unsupported tool handlers must not be presented as working actions.

## 1. Context

The Voice AI platform uses an immutable versioning model for agent configurations (ADR-0006, RFC-0003). An agent has a mutable top-level identity (`Agent`), multiple version records (`AgentVersion`), and a pointer to the current `active_version_id`.

Draft versions (`status = 'draft'`) are editable using optimistic concurrency control (`revision: number`). Published versions (`status = 'published'`) are strictly immutable and can be cloned into new drafts.

## 2. Goals

- Provide a clear, visual authoring workspace for agents, dialogue flow state machines, prompt assemblies, tool bindings, and voice/model selections.
- Ensure unambiguous distinction between mutable agent identity, immutable published releases, and active draft revisions.
- Offer visual and structured JSON editing for Pipecat `FlowConfig` nodes, state transitions, and node-scoped tool bindings.
- Include pre-publication validation, draft diffing against published releases, and atomic activation.

## 3. Non-Goals

- Tenancy-based agent isolation (single workspace scope).
- Live execution within the editor without initiating a real run or test harness session.

## 4. Routes

- `/agents` — List of all agents, their active versions, personas, and recent run metrics.
- `/agents/:agentId` — Agent overview, release history, draft status, and version comparison.
- `/agents/:agentId/versions/:versionId` — Version editor with focused tabbed panels:
  - `?tab=prompts` — System instruction, persona, tone rules, and variable templates.
  - `?tab=flow` — Visual dialogue state machine, node prompts, transitions, and terminal nodes.
  - `?tab=models` — Provider selection (Sarvam STT/TTS, Groq LLM, Cartesia TTS) and voice options.
  - `?tab=tools` — Tool bindings (`change_node`, `send_whatsapp_template`, `end_call`).
  - `?tab=knowledge` — Attached knowledge bases and retrieval thresholds.
  - `?tab=cadence` — VAD timing, turn limits, max duration, and interruptibility settings.

## 5. API Dependencies

### Consumed Existing APIs
- `GET /api/v1/agents` — List all agents.
- `POST /api/v1/agents` — Create new agent with initial Version 1.
- `GET /api/v1/agents/{agent_id}/versions` — List all version records for an agent.
- `PATCH /api/v1/agent-versions/{version_id}` — Save draft configuration with expected revision.
- `POST /api/v1/agent-versions/{version_id}/publish` — Validate and publish immutable version.
- `POST /api/v1/agent-versions/{version_id}/clone` — Create a new draft incremented from an existing version.
- `POST /api/v1/agents/{agent_id}/activate` — Set the active published version for new calls.
- `PUT /api/v1/agent-versions/{version_id}/tools` — Bind a published tool version to a draft key.
- `GET /api/v1/tools` & `GET /api/v1/tools/{tool_id}/versions` — Pinned tool lookup.
- `GET /api/v1/knowledge-bases` — Knowledge base selection.
- `GET /api/v1/providers` — Provider slot and model options.

## 6. Layout & Feature Components

### 6.1 Version Editor Layout
```text
┌────────────────────────────────────────────────────────────────────────┐
│ [← Agents] Maya (Omkar's Assistant)  [v1 Draft • Rev 3]  [Save] [Publish]│
├────────────────────────────────────────────────────────────────────────┤
│ [Prompts] [Flow Nodes] [Voice & Models] [Tools] [Knowledge] [Cadence]   │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  [Node List / Graph]           │  [Node Inspector Pane]                │
│  ├── greeting (initial)        │  Node ID: greeting                    │
│  ├── brand_recap               │  Prompt Template:                     │
│  ├── timeline_and_assets       │  "Warmly greet Deepankar..."          │
│  ├── whatsapp_catalog          │                                       │
│  ├── callback_scheduling       │  Transitions: [brand_recap, exit]     │
│  └── closing (terminal)        │  Allowed Tools: [change_node, end]    │
│                                │                                       │
└────────────────────────────────────────────────────────────────────────┘
```

### 6.2 Key Components
- `FlowGraphEditor.tsx`: Interactive node graph with transition arrows, initial node marker, and terminal indicators.
- `PromptTemplateEditor.tsx`: Monospace editor with syntax highlighting, token count estimation, and variable autocomplete.
- `ToolBindingSelector.tsx`: Matrix mapping binding keys (`change_node`, `send_whatsapp`) to published tool versions (`ToolVersion`).
- `VersionDiffModal.tsx`: Visual side-by-side JSON diff comparing the current draft against the active published release.
- `PublishValidationBanner.tsx`: Pre-flight checklist verifying tool bindings, valid transitions, and non-empty prompt slots before enabling the publish button.

## 7. Concurrency & Immutability Rules

1. When opening a draft, the UI stores the retrieved `revision: number`.
2. All `PATCH` requests pass `{ revision: currentRevision, config: ... }`.
3. If another session updated the draft (HTTP 409), the UI halts auto-save and displays a `ConflictResolutionBanner` prompting the user to review changes.
4. Published versions disable all form inputs and display an action: `Clone to New Draft (v{N+1})`.

## 8. Open Questions & Iteration Notes

1. *Visual Node Dragging vs Form-first Node List*: Should the initial implementation use a rich form list with transition select boxes, or a full canvas (React Flow)? (Recommended: start with form-first list + SVG layout preview for maximum reliability and keyboard accessibility).
