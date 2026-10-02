# Runtime evidence and Pipecat implementation plan

This plan preserves every finding from the user-provided review. The source text is copied verbatim to [attached-implementation-review.txt](../references/attached-implementation-review.txt). Findings are treated as review hypotheses until verified against current code and tests.

## Prioritized findings

### P1

1. **WhatsApp connection binding mismatch.** Verify that inbound 24-hour window checks and sends both use the same pinned connection. Update `tool_dispatch.py` to pass and enforce the connection identity through both operations; reject mismatches and avoid selecting the first enabled connection as a fallback when an authorization check was performed against another account. Add tests with two enabled WhatsApp connections.
2. **Misclassified runtime errors.** In the evidence observer, map only recognized LLM, STT, and TTS processors to those categories. Record unrecognized processors as `runtime`/`unknown`; never end an active TTS span for unrelated pipeline errors. Test transport and generic processor failures.
3. **Misleading first-token average.** Filter the run summary to LLM spans with a recorded TTFB and label it as LLM first-token latency. Test that STT/TTS spans do not affect the value and update the dashboard label.

### P2

4. **Provider labels use class names or constants.** Use normalized provider identifiers already supplied to the observer for STT/TTS spans. Add coverage for Sarvam STT and configured TTS services.
5. **Span inspector shows inapplicable fields as missing.** Render non-null, category-applicable measurements first; place omitted measurement coverage in a compact expandable section. Keep missing distinct from measured zero.
6. **Incomplete Pipecat metrics.** Capture STT audio seconds, TTS character usage, and text aggregation latency from their native metric frames. Associate each measurement with the correct span and show it in the run inspector and summary.
7. **STT end-of-turn latency (TTFS).** Measure monotonic time from VAD stop to final transcript, label it distinctly from LLM TTFB, persist it as evidence, and surface it for voice-turn tuning. Handle missing final transcript and repeated VAD events safely.
8. **Error classification and recoverability evidence.** Persist Pipecat `ErrorCategory` and processor `is_usable` where available, alongside safe diagnostics. Preserve current fail-fast call behavior unless a tested recovery policy is added; expose retryability and category without secrets.
9. **Voicemail detection absent from outbound call setup.** Verify current Pipecat API and add a post-STT voicemail/person gate before agent speech. Ensure voicemail greeting audio is not interrupted by bot TTS, record the decision in evidence, and test positive, negative, timeout, and inconclusive cases.
10. **Idle escalation fixed in code.** Move idle reprompt text and retry count into typed agent configuration with defaults matching current behavior. Keep Pipecat's idle event mechanism and preserve safe hangup behavior. Add schema, runtime, editor, and default-compatibility tests.

### P2 follow-up from the pasted review

11. **Transcript event choice needs evidence.** The current pipeline is cascaded STT→LLM; verify the pinned Pipecat event semantics and use the standard user-turn-stopped event if appropriate. Keep realtime-specific handling only for realtime transports where message content may be absent. Test transcript content, interruption state, and duplicate suppression.
12. **Reconcile stale project status.** Update the relevant runtime plan/memory entry to reflect that `NativePipelineHost` exists, while retaining actual missing work such as voicemail detection and metrics. Do not rewrite unrelated historical notes.
13. **Run inspector structure.** Group evidence by setup, caller speech, inference/tools, synthesis/playback, and termination; distinguish browser cleanup, local output completion, and Twilio marks/readback. Link diagnostics to provider operation spans where correlation exists.
14. **Keep end-to-end lifecycle contracts explicit.** Preserve browser-session cleanup, SIM7600 claim/dial/hangup verification, Twilio authenticated callback and playback mark ownership, and durable evidence-spool completeness while making the above changes. Tests must not dial real contacts or require live providers.

## Execution order

1. Verify each finding against the copied-main code and existing tests; mark false positives with evidence.
2. Fix the P1 correctness and reporting errors with focused unit/API/dashboard coverage.
3. Add missing telemetry and category-specific inspector presentation.
4. Add voicemail and idle configuration as separate runtime slices with provider/hardware-independent tests.
5. Reconcile transcript event use and project status docs.
6. Run narrow tests/lint, inspect the combined diff, and record any Pipecat behavior not testable without provider credentials or modem hardware.

## Pipecat Flows implementation linkage

The native Flows migration remains the separate sequence in [01-migration-sequence.md](01-migration-sequence.md). Do not let the diagnostics work replace or silently drop the user's flow requirements: system-level `role_message` per active node objective, declarative `FlowConfig` construction, transition/branch tables, pre/post-actions including `tts_say`, global functions, operator-defined fact capture into `FlowManager.state`, configurable initial node/order, removal of the separate verbatim greeting, and opt-in incomplete-turn filtering with default false.


## Fresh-database validation after merging main

The worktree was fast-forwarded from `dd6a579` to local `main` at `cbc60fd`; `main` itself was not modified. An isolated PostgreSQL 16/pgvector database using project `codex-flow-validation` and host port `55433` reached `0043_remote_artifact_guard`. The first clean upgrade exposed a bootstrap assumption in migrations `0028_stable_legacy_org_and_audit` and `0029_stage_org_columns`: both required a verified platform-owned legacy organization even when the database and all customer tables were empty. The migrations now allow an empty legacy mapping only for that fully empty state; they still fail when existing users/orgs/admins or customer rows cannot be mapped. Verification found zero organizations, zero platform admins, and zero legacy mappings after migration. API `/health` returned `ok`.

Runtime verification after merge: all unit tests passed, Ruff passed, the dashboard TypeScript check passed, and Vite produced a production build in the task visualization output directory. The dashboard OpenAPI types were regenerated from the merged contract and include `FlowFunctionConfig`, `FlowBranchConfig`, and `filter_incomplete_user_turns`. No signed-in dashboard session or live provider call was run: this worktree has no dashboard Clerk publishable key, provider credentials, or telephony hardware. The FastAPI docs panel is open at `http://127.0.0.1:8766/docs`.
