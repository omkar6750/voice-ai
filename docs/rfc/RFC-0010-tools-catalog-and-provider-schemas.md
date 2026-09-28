---
id: RFC-0010
title: Tools catalog, versioned schemas, and provider registry surface
status: Proposed
version: 1
date: 2026-09-23
authored_by: omkar
related: [RFC-0001, RFC-0003, RFC-0004, RFC-0005]
---

# RFC-0010 · Tools catalog, versioned schemas, and provider registry surface

## Implementation amendment, 2026-09-24

- Current tool routes support definition/version editing. Published versions are immutable; clone to edit. Agent version pins exact version; node selects binding key.
- Show handler as available only when runtime dispatches it. Derive provider setting choices from reviewed backend contracts and installed support. Schema validation and successful execution are separate checks.

## 1. Context

Tools in the Voice AI platform (`change_node`, `end_call`, `send_whatsapp_template`, `classify_lead`) represent discrete executable capabilities available to the LLM during conversational turns.

Like agents, tools use immutable versioning (`ToolVersion`):
- Draft versions allow updating description, JSON schema parameters, and timeout settings.
- Published versions are locked and can be referenced by agent tool bindings (`AgentVersionTool`).
- The system also exposes a Provider Catalog (`GET /api/v1/providers`) detailing available STT, LLM, TTS, and embedding models.

## 2. Goals

- Provide a central Tool Catalog displaying available system tools and custom integration handlers.
- Offer an interactive **JSON Schema Editor & Validator** for tool parameters.
- Provide a Provider & Model Registry view showing active AI providers (Sarvam, Groq, Cartesia, Gemini), supported slots, and recommended configurations.
- Allow operators to test tool schemas against sample argument payloads.

## 3. Non-Goals

- Dynamic arbitrary Python code execution uploaded directly from the browser (tool handlers reference backend protocols and verified adapter keys).

## 4. Routes

- `/tools` — Tool catalog showing all tools, published version counts, and agent bindings.
- `/tools/:toolId/versions/:versionId` — Tool schema editor with draft/published state.
- `/providers` — Active AI provider slots, models, and contract schemas.

## 5. API Dependencies

### Consumed Existing APIs
- `GET /api/v1/tools` — List all tools.
- `POST /api/v1/tools` — Create a new tool.
- `GET /api/v1/tools/{tool_id}/versions` — List all version records for a tool.
- `PATCH /api/v1/tool-versions/{version_id}` — Update draft tool schema with revision lock.
- `POST /api/v1/tool-versions/{version_id}/publish` — Publish tool version.
- `POST /api/v1/tool-versions/{version_id}/clone` — Clone published tool into new draft.
- `GET /api/v1/providers` — Provider slot and model matrix.
- `GET /api/v1/config-schema` — Base Pydantic contract schemas.

## 6. Layout & Feature Components

### 6.1 Tool Editor Layout
```text
┌────────────────────────────────────────────────────────────────────────┐
│ [← Tools] send_whatsapp_template  [v1 Published]  [Agent Bindings: 2] │
├────────────────────────────────────────────────────────────────────────┤
│ Description: "Send pre-approved WhatsApp follow-up template..."        │
├────────────────────────────────────────────────────────────────────────┤
│ Parameter JSON Schema:                                                 │
│ {                                                                      │
│   "type": "object",                                                    │
│   "properties": {                                                      │
│     "caller_name": {                                                   │
│       "type": "string",                                                │
│       "description": "Caller's stated name"                            │
│     }                                                                  │
│   },                                                                   │
│   "required": ["caller_name"]                                          │
│ }                                                                      │
└────────────────────────────────────────────────────────────────────────┘
```

### 6.2 Key Components
- `JsonSchemaEditor.tsx`: Visual schema builder and raw JSON editor with real-time schema validation.
- `ProviderSlotMatrix.tsx`: Visual grid showing slots (`STT`, `LLM`, `TTS`, `Embedding`, `Classifier`) mapped to their configured providers (`Sarvam`, `Groq`, `Cartesia`, `Gemini`).
- `ToolTestHarness.tsx`: Interactive argument validator checking whether sample payloads conform to the tool's parameter schema.

## 7. Open Questions & Iteration Notes

1. *Schema Linting*: Ensure the schema editor enforces strict JSON Schema Draft-07 conventions required by OpenAI / Groq tool calling formats.
