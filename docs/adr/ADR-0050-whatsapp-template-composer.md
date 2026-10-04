# ADR-0050: Per-template WhatsApp composer

Status: Accepted locally, 2026-10-04.

## Decision

Keep approved Meta template text and pinned tool versions unchanged. A saved agent version may enable a composer with one LLM provider/model/credential and a separate system prompt and required HTTPS URLs for each bound WhatsApp template tool.

The conversational agent chooses the tool and may supply a caller-confirmed recipient number. It does not supply template body text. The composer receives the entire ordered, finalized Caller/Agent transcript as its only user message, apart from its configured system instruction. Tool calls, tool results, summaries, facts, context messages and flow prompts are excluded. Text-chat safe checkpoints retain this plain transcript separately from the LLM context so summarization and resume do not shorten it.

Validate that the composer returns exactly the pinned template's dynamic fields, each nonempty and within Meta's 1024-character parameter limit, and that configured URLs are present. A failed or ambiguous composition must stop before the WhatsApp broker is called. The selected provider, credential, and model use the same stage credential resolution as other LLM calls. The successful composition is recorded separately from the WhatsApp send result.

## Consequences

Composer model calls add cost and latency, and the full transcript may contain personal information. Operators select a stored provider credential and review the per-template prompt and URLs before enabling. Full transcript input, composed output, provider/model, duration, and failures are recorded in run evidence. Existing agents without composer settings continue using their pinned tool behavior.
