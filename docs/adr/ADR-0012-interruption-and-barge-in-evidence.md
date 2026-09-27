# ADR-0012 · Interruption and barge-in evidence

Status: Accepted  
Date: 2026-09-27  
Related: [PLAN-0012](../plan/PLAN-0012-waterfall-barge-in-and-interruptions.md),
[ADR-0010](ADR-0010-tool-context-delivery-evidence.md),
[ADR-0011](ADR-0011-classifier-entry-exit-execution.md)

## Context

The runtime observed caller speech, STT, LLM, TTS, playback, and Pipecat
interruption frames, but the evidence contract did not express their causal
relationships. A barge-in could therefore look like a generic playback stop,
tool cancellation could be duplicated by a handler cleanup path, and a null
provider output could not be distinguished from an empty, interrupted, or
not-applicable output. The dashboard sorted mostly by timestamps and did not
show the interruption as the cause of cancelled work.

## Decision

Use an explicit interruption event plus parent-linked operation spans.

`InterruptionRecord` is the durable event. It records the source, reason,
Pipecat frame type, exchange, and the IDs of active operations and tools that
were interrupted. Operation completion records carry `interruption_id` and an
explicit `output_state`. Tool completion records carry the same interruption
link and use `status="cancelled"` with a structured cancellation result.

Keep caller speech and STT as separate spans. STT is a provider conversion
operation caused by speech; it is not the same measurement as captured speech.
The causal links are:

```text
caller speech
  └── STT
  └── LLM inference
        └── TTS synthesis
              └── serial playback
                    └── interruption / cancellation link
```

The runtime tracker owns interruption closure and makes it idempotent. It
closes active non-speech/STT operations and active tools once. A later handler
`finally` block checks whether the tool was already ended before emitting a
second terminal record.

## Contracts and data flow

The evidence contract now includes:

- `OperationStarted.parent_id`.
- `OperationEnded.output_state` with `recorded`, `not_applicable`,
  `not_recorded`, `empty`, `interrupted`, or `failed`.
- `OperationEnded.interruption_id` and `ToolEnded.interruption_id`.
- `InterruptionRecord` with operation/tool cancellation IDs.

The API persists interruption events in `interruption_events`, adds output and
interruption fields to `trace_spans`, and adds interruption linkage to
`tool_invocations`. Evidence ingestion validates all referenced IDs belong to
the same run. The timeline response returns interruption events alongside
spans and tools.

Migration `0019_interruption_evidence` is the single development schema change;
there is no compatibility branch for older published shapes.

## Runtime behavior

`EvidenceObserver` deduplicates the same `InterruptionFrame` by frame identity,
calls the tracker with `source="caller"` and `reason="caller_barge_in"`, and
clears the active local LLM/TTS/playback references after the tracker closes
them. Speech and STT remain active so their normal terminal frames can record
the caller utterance and transcription separately. LLM and TTS output are
represented independently: LLM output is generated text, while TTS output is
spoken text.

Output state is derived when a completion does not provide one explicitly:
interrupted/cancelled statuses become `interrupted`, failed operations become
`failed`, speech/playback become `not_applicable`, missing payload becomes
`not_recorded`, empty text becomes `empty`, and non-empty output becomes
`recorded`.

## UI behavior

The waterfall keeps operations separate but indents child spans by their
causal parent. Barge-in rows show the reason and counts of interrupted
operations/tools. The inspector shows interruption identity and output state;
LLM spans are labelled as generated text and TTS spans as spoken text. An
interruption row can be selected to inspect its source, frame, reason, and
cancelled IDs.

The API contract continues to flow through Pydantic response models, OpenAPI
export, generated dashboard types, and the typed dashboard code.

## Verification

- Runtime regression test covers one interruption, active LLM/TTS/playback
  closure, cancelled tool linkage, parent links, and idempotency.
- API integration coverage was added for evidence ingestion and timeline
  replay. The repository’s integration fixture gate skipped that module in the
  current environment, so a live database-backed run remains manual follow-up.
- Migration applied successfully and is at the Alembic head.
- Focused Ruff passed.
- OpenAPI export, dashboard type generation, and production dashboard build
  passed.
- No demo or seed scripts were changed.

## Known limitations

- A live modem/browser call with a real caller barge-in was not run here.
- The current interruption observer treats `InterruptionFrame` as caller
  barge-in. Provider/system/transport-specific causes belong to the structured
  diagnostics work in Plan 0013.
- The timeline still stores one event per operation rather than raw audio or
  per-token events. This is intentional for evidence volume and privacy.
