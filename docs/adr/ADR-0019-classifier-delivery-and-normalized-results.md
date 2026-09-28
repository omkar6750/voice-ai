# ADR-0019: Unified classifier delivery and normalized results

Status: Accepted

## Decision

The active runtime exposes exactly one registered classifier tool, `classify_lead`.
The agent configuration selects exactly one backend (`llm` or `jev`); automatic node
classification and the dynamic tool use that same selection. Provider-specific
configuration is stored only under the selected branch for new versions. Legacy
dual-branch records remain readable and are normalized on the next draft save.

Groq and Gemini inference in the configurable runtime is owned by Pipecat's
`GroqLLMService` and `GoogleLLMService`, using the public `LLMContext` and
`run_inference` APIs. JEV remains a direct provider adapter because no Pipecat
JEV service exists. The protected standalone demo remains a documented legacy
exception and is not changed by this migration.

## Context boundary

Automatic classifier results are semantic `system` task messages supplied through
Pipecat Flow `NodeConfig`; node transitions use `ContextStrategy.RESET` when the
new task replaces the old task. Dynamic `classify_lead` results are delivered by
Pipecat as `tool` messages with their matching `tool_call_id`. Application code
does not manually translate provider roles or rebuild private context state.

Both providers normalize to a bounded result containing only configured labels,
for example `{"lead_temperature":"warm","service_fit":"strong_fit","tone":"receptive"}`.
Raw output, probabilities, confidence, questions, criteria, provider metadata,
diagnostics, and explanatory prose are excluded from model-visible context.
Failures use `{"status":"error","code":"classifier_unavailable"}` in context;
detailed diagnostics remain evidence metadata.

## Database transition

Migration `0023_collapse_classifier_tools` rewrites draft and published agent
configurations and relational bindings, preserves historical binding names and
results, nulls only deleted tool-version foreign keys, and deletes every version
and logical tool named `classify_jev` or `classify_llm`. The migration is the
explicit exception to the published-version guards and asserts one logical
`classify_lead` tool remains.

## Consequences

Classifier context no longer creates unsupported provider role sequences or
unbounded provider payloads. The active runtime has one tool contract and one
dispatch path. Summarization remains pending until implemented through the same
Pipecat provider/context boundary; no direct summarizer inference path may be
added. Model discovery, JEV, WhatsApp, database, and test transport HTTP calls
remain separate non-LLM boundaries.
