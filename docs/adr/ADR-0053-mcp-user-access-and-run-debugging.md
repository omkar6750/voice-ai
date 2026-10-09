# MCP user access and selective run debugging

Status: accepted. Date: 2026-10-08.

The API control plane serves stateless Streamable HTTP MCP at `/mcp`. A token is
a revocable, expiring capability bound to one local user, organization and
environment. Only a SHA-256 hash of its randomly generated 256-bit secret is
stored. Clerk sessions create and revoke tokens; an MCP token cannot manage
tokens, credentials, OAuth connections or platform administration.

Every MCP request checks the token, enabled account and live Clerk membership.
Tool execution checks membership again. An in-process ASGI scope object carries
the authenticated principal into existing HTTP routes; client headers cannot
supply it. Existing member/admin permissions, tenant filters, revision checks
and immutable published versions remain authoritative. No MCP-specific admin
privilege or cached role is introduced. Clerk lookup failures fail closed.

Tool schemas come from OpenAPI, with an explicit reviewed operation manifest.
New routes require a manifest decision and are not exposed automatically. There
is no generic HTTP proxy tool. Credential metadata is readable and credential
IDs can be selected in configurations. Credential writes, secret rotation,
OAuth setup and connection deletion that clears credentials are excluded.
Knowledge uploads use a bounded base64-to-multipart adapter through the same
HTTP validation. Mutations have a durable pre-dispatch audit entry and final
outcome; a remaining `started` entry represents an unconfirmed outcome. External
actions and publication must not be retried automatically after an uncertain
response. PostgreSQL rate buckets work across API workers.

Run debugging starts with `inspect_run`: one full transcript, exchange and node
references, compact logical operations, API attempts, timings, error references,
coverage and factual findings. Input/output bodies and LLM context are absent.
`inspect_operations` batches selected IDs and requested sections. Context is
explicit and content-addressed, with exact unambiguous transcript messages
referenced instead of repeated. A caller can explicitly materialize context.
`get_run_config` reads the immutable run snapshot; `read_run_logs` filters
diagnostics and retained private log artifacts. Large responses use explicit
offset/hash continuation rather than silent truncation.

Request metadata is captured independently of optional outbound logging. HTTPX,
requests, httplib2 and aiohttp adapters record attempts, failures and timing
scope. Modern websockets connection creation records transport setup; logical
STT/TTS spans describe speech execution. Hooks never consume audio or provider
streams. Buffered JSON bodies are captured only when the run's existing
`pipeline_logs_enabled` policy allows it, bounded to 1 MB and redacted before
runtime persistence. Backend tool requests currently persist metadata only.
Legacy SDK transports, historical runs, stream bodies and payloads disabled by
policy are explicitly unavailable; zero recorded requests does not prove zero
network activity. Completeness of stored evidence and completeness of network
instrumentation are separate claims.

Production requires a configured HTTPS public MCP base URL. Development uses
the configured local URL and permits plaintext HTTP only on loopback. The
transport validates Host and optional Origin, and the dashboard displays the
environment-specific URL, one-time token and an environment-variable-based
Codex registration command. Secrets are not persisted in browser storage or
Codex's server configuration.
