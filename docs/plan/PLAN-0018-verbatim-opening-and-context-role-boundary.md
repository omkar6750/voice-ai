# PLAN-0018 · Verbatim opening and context-role boundary

Status: Implemented

## Scope

Implement only the verbatim opening, its dashboard semantics, provider-neutral
context handling, legacy persona removal, and regression tests. Generic actions
and unrelated runtime work are out of scope.

## Implementation

- Render 'greeting' placeholders from the already-whitelisted flow state.
- Emit a Pipecat 'TTSSpeakFrame' with context append enabled when the greeting
  is populated.
- Require the initial node to wait for caller speech in that mode.
- Preserve the existing empty-greeting path.
- Remove persona from active authoring/runtime behavior while accepting legacy
  persisted values.
- Keep system instructions separate and use 'user' for node task messages.

## Verification

- Contract validation covers greeting timing and legacy persona input.
- Runtime tests cover variable rendering, static opening, empty-greeting
  compatibility, and provider-safe roles.
- Dashboard TypeScript/build checks cover the revised labels and controls.
