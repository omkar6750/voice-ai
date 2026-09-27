# ADR-0013 · Canonical runtime diagnostic model

Status: Accepted  
Date: 2026-09-27  
Related: [PLAN-0013](../plan/PLAN-0013-runtime-diagnostics-and-provider-errors.md),
[ADR-0007](ADR-0007-exchanges-and-integration-secrets.md),
[ADR-0012](ADR-0012-interruption-and-barge-in-evidence.md)

## Context

Runtime failures were commonly written as `Pipeline execution failed: ...` in
`Run.error`. That lost provider HTTP status, quota versus throttling semantics,
request IDs, retryability, uncertainty, and the modem state near a cellular
disconnect. Browser and Twilio finalizers could also overwrite a meaningful
outcome with a generic failure string. The run inspector had no structured
diagnostic collection and therefore could not explain why an agent stopped.

## Decision

Use one append-oriented `RunDiagnostic` record as the canonical structured
failure/outcome representation. `Run.error` remains a compact final summary for
existing callers, but detailed UI and operational reasoning comes from
`run_diagnostics`.

The record fields are:

```text
severity, category, source, code, message, detail,
retryable, uncertain, provider_request_id, http_status,
retry_after_seconds, metadata, occurred_at
```

The allowed sources are `provider`, `modem`, `transport`, `call`, `evidence`,
and `runtime`. Categories are intentionally extensible strings so provider- and
transport-specific codes can be preserved without changing the schema for every
new SDK. The UI receives normalized categories and redacted details, not raw
provider response bodies or credentials.

## Data flow and contracts

There are two legitimate ingestion paths and they converge on the same table:

```text
Pipecat/modem/provider runtime
  ├─ ExchangeTracker diagnostic evidence
  │    └─ evidence ingestion ─┐
  └─ terminal runner progress ─┤
                               └─ RunDiagnostic
                                      └─ timeline API
                                           └─ run inspector
```

The typed evidence union now accepts `DiagnosticRecord`. Terminal execution
progress accepts a bounded list of typed `DiagnosticInput` values for failures
that occur after evidence delivery has stopped. IDs make retries idempotent and
conflicting replays fail rather than silently changing history.

The API exposes `DiagnosticResponse` in the typed timeline response. The
contract flow remains Pydantic schemas → FastAPI response model → OpenAPI export
→ generated TypeScript → dashboard rendering.

## Normalization rules

- HTTP 401/403 or credential messages become
  `provider_authentication` and are not retryable.
- HTTP 429 with quota, credit, usage-limit, or billing signals becomes
  `provider_quota_exhausted` and is not retryable.
- Other HTTP 429/TPM/throttling signals become `provider_rate_limit`, are
  retryable, and preserve `retry_after_seconds` when available.
- HTTP 5xx becomes `provider_unavailable` and is retryable.
- SDK text containing the same signals is classified even when the SDK hides
  the HTTP response. Unknown SDK failures remain `pipeline_failure`.
- Provider response bodies are reduced to provider code/message and request ID;
  raw bodies are not stored.

## Call and modem outcomes

Agent-requested termination is an informational `agent_hangup`. Browser
operator stop and browser transport disconnect are separate diagnostics. A
generic telephony liveness callback produces an uncertain `remote_hangup`.

For SIM7600, termination captures alive/serial/SIM/registration/call state,
RSSI, signal quality, operator, radio, and USB-audio state. Low RSSI is a
separate uncertain `low_signal_observed` warning. It is never promoted to the
termination cause without modem evidence supporting that conclusion. Missing
registration, modem disconnect, and command errors receive distinct codes.

## Runtime and UI behavior

The tracker emits diagnostics into the same durable evidence spool as spans and
tool results. Tool wrappers preserve structured provider diagnostics while
removing private diagnostic fields from the tool result exposed to the model.
Pipeline errors and finalizer failures emit normalized diagnostics. Browser and
Twilio exception finalizers write a direct fallback when the spool may not have
been delivered.

The run inspector renders every diagnostic with severity, category, source,
code, HTTP status, uncertainty, message, and redacted detail. This separates a
caller/operator hangup from provider quota exhaustion, provider throttling,
invalid credentials, modem/network loss, and evidence failure.

## Database changes

- `0020_runtime_diagnostics` creates `run_diagnostics` with ownership,
  category/source/severity checks, retry-delay and HTTP-status checks, indexes,
  and redacted metadata storage.
- `0021_diagnostic_metadata_jsonb` aligns the just-created metadata column with
  the ORM’s PostgreSQL JSONB type.
- No automatic redial policy was added.

## Verification and limitations

- The complete unit suite and focused diagnostics suite pass.
- OpenAPI export, generated dashboard contracts, dashboard production build,
  and focused Ruff checks pass.
- The API replay test is present but requires the repository’s isolated
  `VOICE_TEST_DATABASE_URL` gate to run.
- `alembic check` still reports baseline drift from earlier plans, explicitly
  including the interruption JSON columns from Plan 0012. The new diagnostic
  table itself is aligned after migration 0021.
- A live provider quota failure and hardware modem disconnect still require
  manual testing with real credentials/hardware; no live call was made during
  this implementation.
