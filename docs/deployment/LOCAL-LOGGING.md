# Local API and runtime logs

Both services load logging options from their own `.env` and `.env.local` files.
Process environment variables take precedence. Local development overrides:

```dotenv
VOICE_ENABLE_INBOUND_API_LOGS=true
VOICE_ENABLE_OUTBOUND_API_LOGS=true
VOICE_LOG_LEVEL=INFO
VOICE_LOG_FORMAT=pretty
VOICE_LOG_COLOR=always
VOICE_DEBUG_PERF=true
```

`VOICE_LOG_FORMAT=auto` selects nested output for terminals and JSON for redirected
streams. Use `json` for machine collection. `VOICE_LOG_COLOR=auto` colours terminals,
`always` also colours redirected output viewed in PowerShell, and `never` disables
colour. `NO_COLOR` disables automatic colour. Restart services after changing these.

Inbound requests are cyan, outbound requests magenta, operational events green,
4xx/warnings yellow, and 5xx/errors red. Each request includes nested redacted input,
output, trace and span IDs. Streaming media is never consumed for diagnostics.
Milliseconds are rounded to four decimal places; the console displays `27.0000 ms`.
JSON timing values remain numeric. Local rotating files in `data/logs` remain JSONL.

Performance probes only run in development. The loop probe reports five-second
windows only when at least one scheduling delay reaches 40 ms, avoiding routine
Windows timer jitter. This does not change runtime admission/overload checks.

SDK logs retain severity only (`untrusted_log`); application diagnostics must use
trusted event helpers. Provider credentials and caller content stay redacted.
The local launcher redirects console output into `data/local-service-logs`.
