# Hosted demo acceptance record

Every unchecked item is a release blocker for its feature. `/health` proves process
liveness only. Passing static configuration tests does not permit calls. Keep
`VOICE_ENV=production` and `VOICE_HOSTED_CALLS_ENABLED=false` until measured Render
acceptance is recorded. See [deployment contract](../deployment.md) and the parent's
[PLAN-0042](../plan/PLAN-0042-secure-hosted-credentials-and-recordings.md).

## Offline and configuration gates

Local deployment validation was extended on 2026-09-30: the full suite passed with
647 tests and 41 intentional skips, repository-wide Ruff passed, and the dashboard
production build succeeded. Focused coverage included 36 deployment/admission/cleanup
tests and 64 credential/redaction/runtime tests. The
linux/amd64 production image built from a secret-filtered context, started as UID/GID
10001, and returned 200 from `/health`. Python was 3.12.14; the lock SHA-256 was
`0b11c66a1e505e06d3c856962aa03b588ce256d9954ab8b417ae046a2ab8f43d`; the resolved
Python base digest was `sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e`
and uv image digest was `sha256:5cb6b54d2bc3fe2eb9a8483db958a0b9eebf9edff68adedb369df8e7b98711a2`.
The local review image ID was
`sha256:d6e8cc4c4d06f64fddddd68cdd9704850d5c38b759f4d170fe68c84187e4398a`.
Source trees and dotenv files were absent from the final image. Earlier 2026-09-29
validation also covered Node 24.13.1 syntax and the official Render JSON schema.
The local PostgreSQL database and the migration graph both reported the single
`0043_remote_artifact_guard` head. No production migration or live platform/provider
measurement was performed. The checklist remains open where it depends on external
services or live capacity.

- [ ] Parent wires hosted admission, one concurrent call and 600-second duration settings;
  tests prove rejection before DB claim/provider effects with hosted calls disabled.
- [ ] Parent enforces browser/Twilio-only transport, modem denial and all automation off;
  rejects missing production credentials and dev-only bypasses.
- [x] Docker lock freshness/frozen install, linux/amd64 image build and nonroot startup
  pass; record Python/uv versions, dependency lock SHA and resolved base-image digests.
- [ ] Native audio/ONNX/provider imports work without hardware or import-time dialing;
  no model download stalls during a live session.
- [x] New deployment static tests, relevant parent suites and lint pass. Official Render
  JSON schema or CLI validation passes; document tool/schema date and any limitations.
- [x] Container has one Uvicorn worker, no migration/scheduler/demo startup and no
  dashboard, credentials, dotenv, recordings or diagnostic build inputs.
- [ ] Netlify Node 24 build succeeds with only the two approved public VITE values;
  forbidden VITE names/dotenv builds fail without value disclosure. Inspect output for
  secret fixtures and unexpected source files. SPA reload/assets and no-store pass.
- [ ] Production Clerk issuer/key, authorized-party/CORS allowlist and organization
  scope pass token replay, expired-token and cross-org authorization tests. Runtime
  service credential cannot authorize dashboard routes. No wildcard CORS or dev origin.
- [ ] Neon TLS/hostname/CA verification and pooled transaction tenant context pass;
  missing DB fails closed. Migrations are explicitly run by an operator over a direct
  existing connection, with preservation/restore checks and pgvector verified.
- [ ] Existing integration key IDs/ciphertexts decrypt after deployment; missing/wrong
  key and inactive ID reject use. Credential owner confirms provider resolution without
  provider-key env vars and redaction across errors/logs/evidence.

## Persistence and ownership gates

- [ ] One combined browser/Twilio admission race, duplicate callbacks, expired leases,
  old/new process overlap and stale owners produce no second external attempt.
- [ ] Restart/crash leaves unknown external outcomes reserved and evidence incomplete;
  explicit reconciliation releases safely without redial or fabricated success.
- [ ] Cloudinary dependency is locked and adapter is wired to finalization, authorized
  bounded reads and deletion. WAV originals/derivatives deny unsigned access; replay
  checks remote identity/checksum without overwrite. Secret/signed URLs stay backend-only.
- [ ] Cloudinary quota telemetry is current; required-recording calls reject unknown or
  exhausted capacity before starting. No paid quota expansion or automatic spending.
- [ ] Supabase adapter is implemented and wired for private source documents and
  sanitized diagnostics; existing bucket access, MIME/byte limits and secret-key client
  semantics pass. No direct frontend bucket access or owner_id-based tenancy assumption.
- [ ] Cross-org upload/read/list/sign/delete and forged object IDs fail before remote
  access; ingestion failure/stale job preserves active chunks; interrupted upload is
  reconciled. No raw credential/provider/recording data in diagnostics.
- [ ] Artifact downloads/errors have API no-store and omit signed URLs; expired access
  denies reads. Operator-only explicit remote deletion excludes active runs/reusable
  media and retains verified deletion evidence. No scheduled cleanup runs.
- [ ] Forced restart during staging/upload/spool demonstrates loss reporting and durable
  delivered evidence. No promise of recovering an ephemeral local spool is made.

## Actual Render measurements before enabling calls

Use approved synthetic browser audio first; the test operator must explicitly authorize
any provider/Twilio traffic and confirm existing free allowance. Never call a contact
as an automated deployment check. Enabling for an isolated measurement must not open
general customer admission; close it again after the test. Record actual values:

| Measurement | Result/evidence | Acceptance |
| --- | --- | --- |
| Commit, image digest, service/region, free plan | Pending | Reproducible tested revision |
| Cold startup, idle wake, model warmup | Pending | No incorrect admission during startup |
| Idle / model-loaded / peak ten-minute RSS | Pending | Below measured free memory with cleanup/upload headroom, no OOM |
| CPU and event-loop lag during streaming/upload | Pending | Operator-approved real-time budget met |
| STT/LLM/TTS and caller-to-audible p50/p95 latency | Pending | Record target budget before test; observed values meet it |
| Browser WebSocket/audio interruption and cancel | Pending | Deterministic single owner and cleanup |
| Twilio signatures, media marks/clear and remote hangup | Pending | Approved test allowance; no duplicate/redial |
| Second concurrent request | Pending | Rejected before external effects |
| Server deadline at 600 seconds | Pending | Transport released; fenced terminal evidence |
| Storage failure / unknown quota | Pending | Required capture blocks or closes; truthful evidence |
| Drain and forced restart | Pending | No new admission, stale owner fenced, no redial |
| Platform/provider budgets | Pending | Free allowance, no auto-purchase/upgrade |

Attach sanitized run IDs/metrics/checksums, not recordings, credentials or signed URLs.
If memory/latency fails, keep hosted calls disabled. A paid upgrade needs separate user
authorization; this plan never silently chooses a larger instance.

## Manual release and rollback checklist

1. Confirm all applicable gates, exact commit, free quotas and no automatic spending.
2. Close the database-backed admission/drain gate. Confirm hosted calls disabled and
   no new provider work can start. Do not use an env redeploy as the drain operation.
3. Let the current run finish (up to ten minutes) and finalize remote uploads/evidence;
   confirm zero live and uncertain claims, or stop for explicit reconciliation.
4. Run only approved direct-connection migrations outside service startup; record head.
5. Operator manually deploys the already-reviewed image/ref; auto-deploy remains off.
6. Verify health, organization auth, private storage and incomplete-run reconciliation.
7. Reopen admission only for accepted browser/Twilio demos; one concurrency, 600 seconds.
8. For rollback, repeat the drain. Verify schema compatibility; never automatically
   downgrade or discard evidence. Keep calls disabled if acceptance no longer holds.

No provisioning, live validation, migrations, scheduled deletion, paid resources,
commit or push is performed by this acceptance file.
