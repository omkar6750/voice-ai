# ADR-0055: SIM7600 connection and release verification

Status: Accepted locally, 2026-10-08.

## Decision

An accepted dial command is not an active voice call. The runner waits for an
active modem state before enabling PCM and starting the greeting. Make that wait
configurable with `VOICE_SIM7600_CONNECT_TIMEOUT_SECONDS` (default 90 seconds),
subject to the existing total call duration limit. A longer wait does not establish
that a SIM, carrier, or modem can complete voice-call setup.

For an outgoing dial attempt, cleanup sends hang-up even when a transient call-list
response is empty. Keep ownership and poll for a stable idle/disconnected interval
before declaring release. A non-idle state resets verification and causes another
hang-up attempt; repeated attempts are bounded and throttled. Defaults are a
15-second stable interval inside a 30-second verification deadline, configurable
with `VOICE_SIM7600_RELEASE_STABLE_SECONDS` and
`VOICE_SIM7600_RELEASE_TIMEOUT_SECONDS`.

On unconfirmed release, retain the existing uncertain-session port fencing. The
API must not give the run an ended timestamp or make the endpoint reusable on the
basis of an accepted hang-up command alone. Connection timeout and unconfirmed
cleanup emit structured run diagnostics.

## Evidence and limits

Two v12 phone runs never progressed past modem dialing during the old 30-second
wait. Their cleanup trusted one empty call-list response just milliseconds after
hang-up. A simulated late call reproduces that verification gap. Regression tests
cover late-call reappearance, persistent dialing, connection-timeout diagnostics,
and retained port ownership on uncertain cleanup. No automatic call or redial is
part of verification; real modem/carrier ringing behavior remains unverified.
