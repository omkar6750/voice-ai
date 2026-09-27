---
id: PLAN-0020
title: Agent architecture workstream index
status: In progress
date: 2026-09-27
related: [RFC-0003, ADR-0006, ADR-0007, PLAN-0018, PLAN-0019]
---

# Agent architecture workstream index

Implementation is in progress. The published agent remains untouched; a separate draft contains the prompt fixes. The language-contract and usage-evidence migrations are applied locally. Preserve the user's exact annotation context in [CONTEXT-2026-09-27](CONTEXT-2026-09-27-agent-architecture-review.md). Do not edit classifier work owned by the concurrent agent, protected `scripts/demo_call.py`, or unrelated drafts. Verify the working tree before each implementation slice.

| Sequence | Plan | Annotation coverage | Dependency |
| --- | --- | --- | --- |
| 1 | [PLAN-0021 prompt/flow](PLAN-0021-ecommerce-agent-prompts-and-tool-references.md) | 1–6 | None; publish a new draft/version, never mutate immutable published config |
| 2 | [PLAN-0022 context/reset](PLAN-0022-flow-state-and-context-reset-verification.md) | 7–8 | RESET verification may proceed; flow-state facts and additional variables are deferred pending discussion |
| 3 | [PLAN-0023 call completion/actions](PLAN-0023-call-completion-and-node-actions.md) | 9 | Lifecycle evidence and SIM test environment |
| 4 | [PLAN-0024 KB binding](PLAN-0024-knowledge-binding-and-result-budget.md) | 10 | Tool binding contract |
| 5 | [PLAN-0025 usage/budget](PLAN-0025-token-accounting-and-groq-budget.md) | 11 | Usage metrics enabled and verified |
| 6 | [PLAN-0026 summarization](PLAN-0026-provider-neutral-summarization.md) | 12 | Plans 0022 and 0025; don't launch until current token accounting works |
| 7 | [PLAN-0027 turn/call controls](PLAN-0027-turn-taking-and-effective-call-controls.md) | 13–15 | Bounded audio test runs |
| 8 | [PLAN-0028 contract audit](PLAN-0028-effective-configuration-and-language-deferral.md) | 16–17 | One-time cleanup of all agent-version configs; preserve historical run evidence |
| 9 | [PLAN-0029 Cartesia](PLAN-0029-cartesia-provider-specific-settings.md) | 18 | Plan 0028 provider-contract classification |

Cross-cutting release gates: unit tests for each contract/runtime/dashboard slice, API-to-generated-TypeScript compatibility, focused integration tests, `uv run ruff check .`, `uv run pytest`, dashboard `npm run build`, a real browser/demo call where relevant, and final SIM7600 carrier verification for timing/hangup. Do not treat an unavailable provider key, database, modem, or older run directory as successful verification. Document the gap. Never silently reinterpret an existing saved control or published version.

References: [Pipecat Flows context strategies](https://docs.pipecat.ai/pipecat/flows/context-strategies), [state](https://docs.pipecat.ai/pipecat/flows/state-management), [actions](https://docs.pipecat.ai/pipecat/flows/actions), [context summarization](https://docs.pipecat.ai/pipecat/fundamentals/context-summarization).
