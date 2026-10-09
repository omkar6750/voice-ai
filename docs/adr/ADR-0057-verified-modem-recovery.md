# ADR-0057: Verify execution and hardware before releasing a modem lease

The endpoint recovery action previously changed expired execution to uncertain,
which intentionally still occupied the endpoint. A success toast did not imply release.

Recovery now holds the endpoint ownership lock while the authenticated runtime
verifies the exact prior generation, stopped execution, successful fresh modem
commands, no active call, disabled USB audio, and exclusive audio-port access.
The runtime reserves both ports during verification. Another active owner,
identity mismatch, unavailable runtime, or inconclusive hardware check blocks recovery.

Only verified recovery marks the previous run/call failed and its runtime assignment
ended. Evidence is explicitly incomplete, with a reconciliation timestamp; no
actual hangup time is invented. Recovery never dials or hangs up an active call.
The dashboard shows the result and blockers instead of unconditional success.
