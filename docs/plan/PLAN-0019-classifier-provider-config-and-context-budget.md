# PLAN-0019: Classifier provider configuration and context budget

1. Collapse historical classifier tools with migration 0023, including published
agent bindings and evidence-safe foreign-key cleanup.
2. Normalize `ClassifierConfig` to mutually exclusive `llm`/`jev` branches and
serialize with `exclude_none=True` at agent persistence and resolution boundaries.
3. Keep one registry/API/dashboard tool, `classify_lead`; route automatic and
dynamic invocations through the selected backend.
4. Execute Groq/Gemini classification through Pipecat services and public
`LLMContext.run_inference`; keep JEV in its direct adapter.
5. Normalize before delivery, allow-list output fields/labels, cap output at 512
characters, and keep diagnostics outside model context.
6. Use semantic Pipecat roles and Flow `ContextStrategy.RESET` for task replacement;
retain caller/assistant history and persona.
7. Keep summarizer execution explicitly pending. When implemented, use the same
Pipecat provider/context path and a bounded context-compaction result.
8. Add migration, dispatch, role/context, normalization, static direct-call, and
dashboard contract tests; run Ruff, Pytest, OpenAPI generation, and dashboard build.
