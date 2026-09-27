# PLAN-0013 · Runtime diagnostics and provider errors

Status: completed

## Existing facts

- Several modem, provider, and pipeline failures currently collapse into generic errors.
- Modem status already includes CSQ, registration, call state, operator, radio, and USB audio fields.
- Provider adapters do not consistently preserve provider error codes/details.

## Scope

- Add one canonical typed diagnostic record.
- Normalize provider, modem, transport, and call termination causes.
- Show redacted actionable errors in the UI.

## Contracts

- Diagnostic fields include severity, category, source, code, message, detail, retryability, uncertainty, provider request ID, HTTP status, retry delay, metadata, and timestamp.

## Runtime and frontend behavior

- Distinguish user hangup, remote hangup, modem disconnect, low signal, provider quota, throttling, authentication, TTS, STT, LLM, and evidence failures.
- Capture modem state near termination without inferring causality from RSSI alone.

## Tests and acceptance

- Provider and modem fixtures preserve normalized codes/details.
- Secrets are redacted.
- User hangup is not shown as a pipeline error.

## Manual verification

- Test modem, provider, quota, credential, and disconnect failures.
- Confirm distinct UI outcomes.

## Non-goals

- No automatic redial policy.

## Implementation

- Added the canonical `RunDiagnostic` model and `run_diagnostics` table. The
  record stores severity, category, source, normalized code/message/detail,
  retryability, uncertainty, provider request ID, HTTP status, retry delay,
  redacted metadata, and occurrence time.
- Added typed runtime/API diagnostic contracts and evidence kind `diagnostic`.
  Both the durable evidence spool and terminal `/runs/{run_id}/progress`
  fallback persist through the same diagnostic table/service.
- Added provider normalization for authentication failures, quota/credit
  exhaustion, throttling/TPM limits, provider unavailability, and generic
  provider failures. Raw provider bodies are not persisted.
- Added pipeline-text classification when Pipecat/SDK errors hide HTTP fields.
  The runtime preserves actionable provider categories while unknown errors stay
  explicit `pipeline_failure` diagnostics.
- Added SIM7600 readiness and termination diagnostics, including a modem snapshot
  near disconnect. Low RSSI is recorded as an uncertain observation and is not
  asserted as the cause of termination. Browser/operator disconnects and agent
  hangup are separate call-termination outcomes.
- Added direct finalizer fallback diagnostics for browser and Twilio pipeline
  failures, plus cleanup, artifact, and evidence-delivery diagnostics for the
  fenced call runner.
- Added diagnostics to the timeline API and run inspector with severity,
  category, provider/source, normalized code, HTTP status, retryability context,
  uncertainty, and redacted detail.
- Added migrations `0020_runtime_diagnostics` and
  `0021_diagnostic_metadata_jsonb`.

## Verification

- Complete unit suite: 91 passed; existing upstream Pipecat deprecation warnings
  and two pre-existing AsyncMock warnings remain.
- Focused provider/runtime/evidence suite: 25 passed.
- Diagnostic tests cover quota versus throttling, provider request IDs, text
  normalization, secret redaction, and runtime evidence validation.
- Browser and Twilio lifecycle tests passed; user/operator termination remains a
  completed call outcome rather than a pipeline failure.
- `uv run alembic upgrade head` applied migrations through
  `0021_diagnostic_metadata_jsonb`; the database reports that revision as head.
- `uv run python scripts/export_openapi.py` passed.
- Dashboard `npm run generate` and `npm run build` passed.
- Focused Ruff passed for all Plan 0013 files.
- Integration coverage was added for diagnostic evidence replay, but the
  integration suite is skipped unless an isolated `VOICE_TEST_DATABASE_URL` is
  configured.
- `alembic check` still reports pre-existing drift from earlier plans
  (`browser_sessions`, classifier JSON, inbound-webhook indexes, and Plan 0012
  interruption JSON columns); it reports no new drift for the diagnostics table.
- No demo or seed scripts were modified. Plan 0014 has not started.

## Boundary

Plan 0013 is complete. The next implementation boundary is Plan 0014
(`tool-and-whatsapp-authoring`); it must not be started as part of this plan.
