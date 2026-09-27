# ADR-0018 · Verbatim opening and context-role boundary

Status: Accepted

## Decision

The existing agent 'greeting' field is an optional verbatim opening. When it is
populated, the runtime renders approved contact/temporal variables, speaks the
result through Pipecat TTS, and waits for caller speech before the initial LLM
turn. The initial flow node must therefore use 'respond_immediately=false'.

When 'greeting' is empty, the existing initial-node LLM behavior remains
unchanged.

The application keeps provider-neutral semantic roles in LLMContext:

- 'system_prompt' is supplied through the provider service's
  'system_instruction'.
- Node task messages use 'user'.
- Caller speech uses 'user'.
- Spoken opening and assistant responses use 'assistant' context aggregation.

Pipecat owns conversion of the context into Groq or Gemini request formats.
The runtime must not manually translate roles for a provider.

The dashboard no longer exposes 'persona'; the runtime does not use it.
Historical persisted configurations may contain the legacy key and are
accepted and ignored during validation so published versions remain readable.

## Context transitions

Node 'append' and 'reset' behavior remains delegated to Pipecat FlowManager.
This change does not alter generic actions or other unrelated runtime work.

## Consequences

Operators can write a guaranteed opening without paying for an LLM response or
having the model rewrite the script. The initial node prompt must describe the
turn after the caller responds and must not repeat the opening.
