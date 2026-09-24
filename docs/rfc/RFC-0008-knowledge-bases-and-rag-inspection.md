---
id: RFC-0008
title: Knowledge bases, document ingestion, and RAG retrieval inspection surface
status: Proposed
version: 1
date: 2026-09-23
authored_by: omkar
related: [RFC-0001, RFC-0003, RFC-0004, RFC-0005]
---

# RFC-0008 · Knowledge bases, document ingestion, and RAG retrieval inspection surface

## Implementation amendment, 2026-09-24

- KB remains mutable. Show active search availability separately from rebuild status; failed rebuild preserves previous index.
- Upload route is POST /api/v1/knowledge-bases/{base_id}/uploads. Chunk inspection and base deletion need backend routes.
- KB ingestion owns splitting/embedding; agent version owns retrieval settings. Search test must identify settings used. Show typed actual scores; RRF score is not a probability. Source deletion invalidates pending ingestion.

## 1. Context

The Voice AI platform supports dynamic retrieval-augmented generation (RAG) through mutable knowledge bases (`KnowledgeBase`). Agent versions pin knowledge base selection and retrieval controls (chunk budget, top-k, fusion weights), while corpus documents and chunks remain mutable (RFC-0003, ADR-0006).

Document ingestion processes raw text, Markdown, and uploaded files (PDF, TXT) into chunked, 768-dimensional normalized embeddings (Gemini embedding model) stored in PostgreSQL with `pgvector`.

## 2. Goals

- Provide a management surface for creating and editing knowledge bases and their ingestion parameters (chunk size, overlap, markdown awareness). Whole-base deletion needs a separate backend contract.
- Support document upload (PDF, TXT, MD) and raw text paste with live ingestion progress tracking.
- Deliver an interactive **RAG Search Tester** allowing operators to simulate semantic and hybrid queries, inspect hit rankings, and evaluate cosine similarity vs. reciprocal rank fusion (RRF) scores before deployment.
- Display chunk-level breakdowns with source attribution and metadata.

## 3. Non-Goals

- Multi-tenant corpus isolation (single workspace scope).
- Historical chunk version storage (retrieval evidence is preserved immutably inside `ToolInvocationResult` per run).

## 4. Routes

- `/knowledge` — List of all knowledge bases with document counts, chunk totals, and agent linkages.
- `/knowledge/:baseId` — Knowledge base workspace with tabbed inspection:
  - `?tab=sources` — Document sources list, upload interface, and rebuild triggers.
  - `?tab=search` — Live RAG search testing console with score breakdown.
  - `?tab=settings` — Chunking configuration, overlap, and supported formats.

## 5. API Dependencies

### Consumed Existing APIs
- `GET /api/v1/knowledge-bases` — List all knowledge bases.
- `POST /api/v1/knowledge-bases` — Create a new knowledge base.
- `PATCH /api/v1/knowledge-bases/{base_id}` — Update knowledge base settings.
- `GET /api/v1/knowledge-bases/{base_id}/sources` — List sources and chunk counts.
- `POST /api/v1/knowledge-bases/{base_id}/sources` — Add text or markdown source.
- `POST /api/v1/knowledge-bases/{base_id}/uploads` — Upload PDF/TXT/Markdown document.
- `DELETE /api/v1/knowledge-bases/{base_id}/sources/{source_id}` — Delete document source and its chunks.
- `POST /api/v1/knowledge-bases/{base_id}/sources/{source_id}/rebuild` — Re-chunk and re-embed document.
- `POST /api/v1/knowledge-bases/{base_id}/search` — Execute hybrid search test query.

### Required Backend Additions
- Source chunk-inspection route with access-controlled excerpts.
- Whole-base deletion contract only if operators need it.

## 6. Layout & Feature Components

### 6.1 Knowledge Base Detail Layout
```text
┌────────────────────────────────────────────────────────────────────────┐
│ [← Knowledge] Neotribe Project Knowledge Base  [Chunks: 14 • Status: Ready]│
├────────────────────────────────────────────────────────────────────────┤
│ [📄 Document Sources (2)]   [🔍 Live Search Tester]   [⚙ Configuration]│
├────────────────────────────────────────────────────────────────────────┤
│ Search Query Console:                                                  │
│ [ "What is the turnaround time for the frontend UI?"           ] [Run] │
├────────────────────────────────────────────────────────────────────────┤
│ Results (Top 3 Hits):                                                  │
│                                                                        │
│ 1. [Rank 1 • Typed scores when returned] Source: Project Brief      │
│    "## Development Status by Omkar                                     │
│     - Backend & Database: 100% built and deployed...                   │
│     - Turnaround Time: 2 to 3 days to deliver the full responsive UI..."│
│                                                                        │
│ 2. [Rank 2 • Typed scores when returned] Source: Project Brief      │
│    "## Client & Brand Overview                                         │
│     - Brand Name: Neotribe                                             │
│     - Brand Evolution: Transitioning from Cyber-sigilism to..."        │
└────────────────────────────────────────────────────────────────────────┘
```

### 6.2 Key Components
- `DocumentUploadDropzone.tsx`: Drag-and-drop file uploader with client-side file-type validation (PDF, TXT, MD) and progress indicators.
- `SourceChunkInspector.tsx`: Collapsible accordion displaying individual source chunks, character lengths, and embedding metadata.
- `RagSearchConsole.tsx`: Interactive test harness with adjustable top-k slider, vector/keyword weight controls, and token budget preview.
- `EmbeddingStatusChip.tsx`: Visual badge indicating whether Gemini embedding is active and configured.

## 7. Open Questions & Iteration Notes

1. *Live Ingestion Polling*: When uploading large multi-page PDF documents, source status transitions from `pending` to `ready`. The UI polls `GET /sources` every 2 seconds until status settles to `ready` or `failed`.
