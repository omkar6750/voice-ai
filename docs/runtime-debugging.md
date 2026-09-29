# Runtime debugging and regression checks

Run commands from the runtime-architecture worktree, not an unrelated checkout.
Use `uv run`; tests use fake credentials and never dial a real contact.

## Focused checks

```powershell
uv run pytest tests/unit/test_end_call_ordering.py tests/unit/test_call_control_params.py --basetemp .pytest_call_verify -o addopts=--strict-markers -q
uv run pytest tests/unit/test_native_termination.py tests/unit/test_runner_termination.py tests/unit/test_termination.py --basetemp .pytest_termination_verify -o addopts=--strict-markers -q
uv run pytest tests/unit/test_callback_http.py tests/unit/test_reconciliation_history.py --basetemp .pytest_actions_verify -o addopts=--strict-markers -q
uv run pytest tests/unit/test_accounting.py --basetemp .pytest_accounting_verify -o addopts=--strict-markers -q
uv run pytest tests/unit/test_speech_service_construction.py tests/unit/test_provider_model_configuration.py tests/unit/test_cartesia_generation_settings.py --basetemp .pytest_speech_verify -o addopts=--strict-markers -q
uv run ruff check .
uv run pytest --basetemp .pytest_regression_suite -o addopts=--strict-markers -q
```

Database integration tests skip without `VOICE_TEST_DATABASE_URL`. Use a separate
test database, never production. Passing mocked tests is not database-concurrency
or browser/hardware/carrier-playback verification.

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
the modem/carrier was released. Browser and Twilio supervisors still need their
separate lifecycle wiring; see the implementation ledger before treating their
existing completed statuses as flow-completion proof.

Missing usage/price is not zero. Accounting uses explicit billable dimensions to
avoid charging gross input plus cached input, or output plus included reasoning
tokens, twice. The independent accounting module is not a current billing report.
