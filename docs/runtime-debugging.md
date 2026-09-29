# Runtime debugging and regression checks

Run commands from the runtime-architecture worktree, not an unrelated checkout.
Use `uv run`; tests use fake credentials and never dial a real contact.

## Focused checks

```powershell
uv run pytest tests/unit/test_end_call_ordering.py tests/unit/test_call_control_params.py --basetemp .pytest_call_verify -o addopts=--strict-markers -q
uv run pytest tests/unit/test_terminal_node_shutdown.py tests/unit/test_graceful_close_deadline.py tests/unit/test_flow_visit_ordering.py --basetemp .pytest_close_verify -o addopts=--strict-markers -q
uv run pytest tests/unit/test_native_termination.py tests/unit/test_runner_termination.py tests/unit/test_termination.py --basetemp .pytest_termination_verify -o addopts=--strict-markers -q
uv run pytest tests/unit/test_browser_termination.py tests/unit/test_browser_cleanup.py tests/unit/test_execution_supervisor_cancellation.py tests/unit/test_native_cleanup_idempotency.py --basetemp .pytest_browser_verify -o addopts=--strict-markers -q
uv run pytest tests/unit/test_callback_http.py tests/unit/test_reconciliation_history.py --basetemp .pytest_actions_verify -o addopts=--strict-markers -q
uv run pytest tests/unit/test_accounting.py --basetemp .pytest_accounting_verify -o addopts=--strict-markers -q
uv run pytest tests/unit/test_speech_service_construction.py tests/unit/test_provider_model_configuration.py tests/unit/test_cartesia_generation_settings.py --basetemp .pytest_speech_verify -o addopts=--strict-markers -q
uv run ruff check .
uv run pytest --basetemp .pytest_regression_suite -o addopts=--strict-markers -q
```

Database integration tests skip without `VOICE_TEST_DATABASE_URL`. Use a separate
test database, never production. Passing mocked tests is not database-concurrency
or browser/hardware/carrier-playback verification.

From `apps/dashboard`, run `node --test tests/browser-peer-lifecycle.test.mjs`
for current/stale peer and reentrant disconnect handling. This tests the event
binding module, not microphone permissions, a mounted React modal, or real audio.
Regenerate contracts with `uv run python scripts/export_openapi.py` at the repo
root, followed by `npm run generate` and `npm run build` in `apps/dashboard`.

## Where to start investigating

| Symptom | Implementation to inspect | Evidence to check |
| --- | --- | --- |
| Tool result lost at end-call | `execution/flow_manager.py` and native `_finish_end_call` | Final tool result, context update, tool end, then end frame |
| Failed call marked successful | `execution/termination.py`, native `_pipeline_failed`, `execution/runner.py` | Requested cause versus observed cause, pipeline finish, independent cleanup status |
| Saved speech setting ignored | `execution/speech.py` | Resolved snapshot selection and constructor arguments; use constructor tests before real providers |
| Callback booking fails | `execution/callback_http.py` and native callback branch | Deployment base URL and HTTP status; logs deliberately exclude body/token details |
| Reconciliation lost old history | API reconciliation endpoint | Existing runtime/final state plus retained top-level audit fields |
| Cost or tokens missing | `execution/observer.py` and `execution/accounting.py` | Operation metrics versus measured attempt coverage; accounting collection/UI is not wired yet |

Run-owned finalized evidence identifies exchanges, operation spans, flow visits
and tool results. Pipeline detail is optional in `pipeline.log` when enabled by
the resolved snapshot. Provider credentials must not be pasted into issue reports
or enabled in frontend logging.

## Interpret termination conservatively

`requested_cause` is the first close intent; `cause` is the retained outcome.
A caller interrupting a graceful goodbye can change the outcome without losing
the original agent intent. Cleanup cancellation must not replace an already
observed immediate caller/network failure. Pipeline errors remain errors even
after an agent requested end-call.

`pipeline_finished_at_ns` proves that the pipeline coroutine returned, not that
Twilio played the last audio sample. `cleanup_status=confirmed` is reported by the
executor only after driver cleanup succeeds. Native close alone does not prove
the modem/carrier was released. Browser context and native host now share the
termination facts; browser cleanup confirms local resource closure, not audible
speaker playback. Twilio now records native termination separately from provider
Call status. Its `twilio_mark` source and confirmed REST release are transport
facts, not human comprehension or flow-completion proof.

Missing usage/price is not zero. Accounting uses explicit billable dimensions to
avoid charging gross input plus cached input, or output plus included reasoning
tokens, twice. The independent accounting module is not a current billing report.

## Twilio checks without an account

```powershell
uv run pytest tests/unit/test_twilio_rest.py tests/unit/test_twilio_protocol.py tests/unit/test_twilio_session.py tests/unit/test_twilio_endpoint_contract.py tests/unit/test_twilio_status_ordering.py tests/unit/test_twilio_stream_ordering.py tests/unit/test_twilio_media_claim.py tests/unit/test_twilio_runtime.py tests/unit/test_twilio_dispatch.py tests/unit/test_twilio_call_api.py -q
```

The tests exercise fake signed callbacks, protocol payloads and HTTP responses.
They include installed Pipecat input/output stop and its actual receive loop;
audio queue internals/providers remain isolated. They never call a telephone
number or use real secrets. No simulated mark proves actual carrier playback.

Start with `telephony/twilio_protocol.py` for authentication/handshake rejection,
`telephony/twilio_session.py` for media/clear/mark/REST release, and API
`twilio_dispatch_service.py` for an uncertain create or duplicate attempt.
`twilio_runtime_service.py` owns Run finalization and independent artifact errors.
Inspect `termination`, `release_status`, `rest_status`, `twilio_dispatch_state`,
`twilio_sequence_number`, `evidence_incomplete` and `artifacts_incomplete` together.
Do not manually reset an uncertain attempt to queued to force a redial.

Before enabling real Twilio calls:

- Configure a reachable canonical `VOICE_PUBLIC_BASE_URL` with HTTPS, a valid WSS
  certificate/443 route, operator token, encrypted account auth token and an
  account-owned voice-capable From number. Do not substitute forwarded host headers.
- Verify deployed WSS handshake signatures, including trailing-slash handling;
  validate account/SID/run identity without logging secrets or media payloads.
- On a consenting test number, exercise terminal goodbye, end-call tool, caller
  hangup, barge-in during goodbye, socket loss, provider error and cancellation.
  Confirm ordered final mark, one REST attempt, terminal readback, and correct
  independent Run and Call outcomes.
- Run actual PostgreSQL races: concurrent dispatch, callbacks versus media claim,
  callback versus finalization, duplicate sockets, and lease/restart reconciliation.
  The mocked row-lock assertions are not transaction-concurrency proof.
- Verify provider playback, account permissions/restrictions, public proxy routing,
  and delayed callbacks/readback. REST ambiguity stays visible and is not retried
  as a write. Restart/manual uncertain-attempt reconciliation remains unfinished.

The current Full-account policy is retained. Twilio's current trial documentation
mentions Media Streams free units but also restricts custom Voice instructions;
do not infer trial compatibility from a free-unit allowance without account checks.
See [Twilio Voice trials](https://www.twilio.com/docs/usage/trials/try-out-voice).
