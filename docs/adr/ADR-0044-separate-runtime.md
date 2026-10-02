# ADR-0044: Separate runtime execution from API control

Accepted 2026-10-02 by the user for the Pipecat Flows worktree.

API owns Clerk, organization authorization, configuration compilation, encrypted
credentials, business tools, DB evidence and artifact access. Runtime owns live
Pipecat sessions, media WebSockets, local SIM7600 and capture. Runtime has no API,
SQLAlchemy, Clerk or vault imports. Existing in-process API modules are retained
as migration reference material until remote route activation is approved.

Use pooled HTTP, stable operation IDs, committed boot/generation assignment before
activation, opaque expiring session grants, and 30-second execution leases. No
waiting call queue or automatic redial. Per-session disk evidence is acknowledged
only after API commit. Operational logs remain separate sanitized file chunks.

Voice and Twilio credentials are handed over once over TLS, held in memory, and
never persisted. Business keys remain API-only. Cloudinary recordings and private
Supabase diagnostics use scoped direct upload grants; API assigns/verifies object
identity and records metadata. Local files stream to API storage.

Local runtime is native Python; production is a separate Docker web service and
rejects SIM7600. Render Free begins at one call with hosted calls disabled until
manual capacity acceptance. Its ephemeral disk does not guarantee crash recovery.
