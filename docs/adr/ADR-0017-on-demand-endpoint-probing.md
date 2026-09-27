# ADR-0017 · On-demand modem connection monitoring

Status: Accepted  
Date: 2026-09-27  
Related: [RFC-0011](../rfc/RFC-0011-runtime-endpoints-and-diagnostics.md),
[ADR-0005](ADR-0005-voice-test-runtime.md)

## Context

The endpoint card displayed online, SIM, network, and RSSI fields, and the API
had a status update route. No code called that route with live modem data. The
SIM7600 adapter could query these fields during a call, but there was no
operator action to check an idle modem, and the dashboard did not refresh its
endpoint data after the page loaded.

## Decision

Add an operator-triggered connection probe. Clicking **Test connection**
performs an immediate read-only AT check. If the modem responds, the browser
repeats the probe every five seconds. Monitoring stops when the modem no longer
responds or a probe request fails; another click starts a new check cycle.

The API locks the endpoint row while probing and rejects probes while a call
owns the modem. This serializes a status check against a new call claim and
prevents concurrent AT commands from competing with call control. Each probe
opens and closes the configured AT port. It persists the timestamp and typed
status snapshot on `RuntimeEndpoint`.

The connection badge means the modem answered `AT`. SIM readiness, voice and
data registration, packet attachment, operator, radio access, band, RSSI, and
signal quality are separate readings. RSSI is shown as the modem's `0–31`
value, with the conventional approximate dBm conversion shown alongside it.
The value is not described as an exact measurement.

## Contract and data flow

```text
Dashboard button
  → POST /runtime-endpoints/{id}/probe
  → lock endpoint and verify there is no active/uncertain call
  → query SIM7600 AT status
  → persist typed EndpointStatus and last_seen_at
  → return typed EndpointProbeResponse
  → update card; repeat in five seconds while AT responds
```

The runtime-endpoint list/detail responses now use Pydantic schemas and are
included in OpenAPI. Existing trace and call lifecycle contracts are unchanged.

## Verification

- `ruff check` passed for the changed backend and modem files.
- OpenAPI export and generated dashboard types completed.
- Dashboard TypeScript and production build passed.
- Hardware behavior requires a SIM7600 connected to the configured AT COM port.

## Limitations

- Monitoring runs in the open dashboard tab and stops when the tab is closed.
- RSSI dBm is a conventional estimate derived from SIM7600's CSQ index.
- SIM identity numbers are not queried or shown.
