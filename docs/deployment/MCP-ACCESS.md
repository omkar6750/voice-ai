# MCP access

Install locked dependencies with `uv sync` and apply migrations with
`uv run alembic upgrade head`. Migration 0051 creates the hashed token, audit and
shared rate bucket tables, with server-only database policies.

Set `VOICE_ENV=dev` for local development and
`VOICE_MCP_LOCAL_BASE_URL=http://127.0.0.1:8000` (the default). For production set
`VOICE_ENV=prod` and `VOICE_MCP_PUBLIC_BASE_URL=https://<public-api-host>`.
The base URL must have no path, query, credentials or fragment. The endpoint is
`/mcp`, outside `/api/v1`. Forward it to the API service, preserving Host and
Authorization; it does not belong on the runtime runner. Keep the usual Clerk
server settings and organization membership directory available.

In the dashboard open Settings → MCP access. Create a named token with a
7-, 30- or 90-day expiry. Copy the token once. Copy Codex command registers the
URL and the name of the environment variable; set that variable before starting
Codex. Copy PowerShell setup sets the current process variable, saves it in the
Windows user environment and runs the registration command. Restart Codex after
setting the persistent environment variable. The copied setup includes the
secret and should be handled as a credential. Revocation takes effect on the
next request, as do membership removal, role changes and disabling the account.
Members manage their own tokens; organization admins can revoke organization
tokens. Platform support sessions cannot issue MCP tokens.

## Debugging workflow

1. Call `inspect_run(run_id)` to obtain the complete transcript and execution map.
   Transcript text appears once; all time offsets use the run's stated origin.
   Check `coverage` and problems before interpreting an apparent gap.
2. Batch relevant span, API attempt, tool, diagnostic or node visit IDs into
   `inspect_operations`, choosing input, output, error, metrics or related_events.
   API attempts link to logical parent operations where known. Overlapping
   durations are not summed into run latency.
3. Request `context` only for relevant operations. Resolve `message_ref` against
   the overview transcript and `content_ref` against the returned contents map.
   Set `materialize_context=true` only when standalone context is necessary.
4. Request a named section from `get_run_config` or filtered `read_run_logs` if
   evidence suggests a configuration or runtime issue. An artifact ID selects
   a retained private log file; expired/deleted artifacts cannot be retrieved.

Bounded responses report continuation offsets and a SHA-256 hash. Supply
`expected_hash` on subsequent chunks to detect a changing live run. Ordinary
overviews fit in one response; oversized runs require explicit continuation.
Unavailable bodies report `not_recorded`. Oversized single log records report
their size and an explicit excerpt; they are not silently claimed complete.

## Maintenance and validation

Run `uv run python scripts/review_mcp_operations.py` after changing OpenAPI.
Review newly added operations in `apps/api/voice_api/mcp_operations.json`;
the registry exposes only approved paths, verbs and schemas. Run
`uv run pytest tests/unit/test_mcp_layer.py` and, with a disposable migrated
PostgreSQL URL in `VOICE_TEST_DATABASE_URL`,
`uv run pytest tests/integration/test_mcp_access.py`.

No hardware or paid provider calls are needed for these tests. Production
reverse-proxy behavior and real provider/hardware execution still require an
environment-specific smoke test. Historical uninstrumented requests cannot be
reconstructed. Do not interpret `request_capture=recorded_attempts_only` as a
claim that every SDK or network packet was captured.
