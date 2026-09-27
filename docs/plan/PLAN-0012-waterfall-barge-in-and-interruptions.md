# PLAN-0012 · Waterfall, barge-in, and interruption evidence

Status: completed

## Existing facts

- The observer sees speech, interruption, TTS, and playback frames.
- Playback interruption is recorded, but LLM/STT/TTS closure and causal links are incomplete.
- The UI currently relies on exchange-level association and timestamp ordering.

## Scope

- Add causal links between caller speech, STT, LLM, tools, TTS, playback, and interruption events.
- Record caller barge-in and cancelled operations.
- Distinguish generated text from spoken text.

## Contracts

- Add interruption/event linkage and explicit output-state fields.
- Keep speech and STT as separate measurements grouped under one turn.

## Runtime and frontend behavior

- Render nested turn lanes rather than independently sorted operations.
- Show interruption reason, audio emitted state, and cancelled operations.

## Tests and acceptance

- User barge-in during LLM generation and TTS playback is recorded correctly.
- Cancelled tool calls are distinguishable from completed tools.
- Null outputs have explicit state.

## Manual verification

- Let the agent speak.
- Interrupt it.
- Inspect caller speech, `InterruptionFrame`, TTS, playback, and LLM/tool statuses.

## Non-goals

- No raw PCM event storage in PostgreSQL.

## Implementation

- Added `InterruptionRecord` evidence with source, reason, frame type, and the
  operation/tool IDs cancelled by the event.
- Added causal `parent_id`, explicit `output_state`, and `interruption_id`
  fields to operation/span evidence; tool invocations now retain their
  interruption linkage.
- Added the `interruption_events` table and migration `0019_interruption_evidence`.
- Made runtime interruption handling idempotent. A caller interruption closes
  active LLM, TTS, playback, and tool work once while keeping caller speech and
  STT as separate measurements that can finish normally.
- Added parent links from STT to caller speech, LLM to speech, TTS to LLM, and
  playback to TTS. Cancelled tools are emitted with a cancellation result and
  the interruption ID.
- Updated the run timeline API and dashboard waterfall to expose interruption
  rows, nested causal indentation, output state, and generated-versus-spoken
  text labels in the inspector.

## Verification

- `uv run pytest tests/unit/test_native_evidence.py -q`: 6 passed.
- `uv run pytest tests/integration/test_operation_evidence.py -q`: 7 skipped by
  the repository integration-environment gate; no integration failures were
  observed because the database-backed test fixture was unavailable to pytest.
- `uv run ruff check` passed for all changed Plan 0012 backend, runtime,
  migration, and test files.
- `uv run alembic upgrade head` applied `0019_interruption_evidence`.
- `uv run alembic current` reports `0019_interruption_evidence (head)`.
- `uv run python scripts/export_openapi.py` passed.
- `npm run generate` and `npm run build` passed in `apps/dashboard`.
- `git diff --check` reported only existing line-ending normalization warnings.
- No demo or seed scripts were modified. Plan 0013 has not started.

## Boundary

Plan 0012 is complete. The next implementation boundary is Plan 0013
(`runtime-diagnostics-and-provider-errors`); it must not be started as part of
this plan.
