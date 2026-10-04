# PLAN-0050 · Hosted runtime and artifact handoff

Status: implementation in progress; hosted deployment awaiting Render workspace confirmation.
Date: 2026-10-04

## Current implementation

`render.yaml` defines separate API and runtime Docker web services. The runtime
image starts one Uvicorn worker on `0.0.0.0:$PORT`. The API owns tenant authorization,
run admission, credential grants, artifact identity and persistent metadata. The
runtime owns a call and its temporary WAV, log and evidence-spool files. It streams
evidence to the API during execution, then asks the API for per-artifact upload
grants, uploads directly to the selected storage provider, and calls `complete`.
The API verifies metadata/content before marking an artifact available. Runtime
files are deleted only after completion. Production mapping is authenticated
Cloudinary `video` assets for WAV recordings and a private Supabase bucket for
sanitized pipeline/runtime logs. PostgreSQL remains the system of record for runs,
fences, evidence and artifact status; the existing hosted plan uses Neon for that DB.

## Service topology and constraints

1. Keep the API and runtime as distinct Render web services in the same region.
   The dashboard reaches only the API. Browser/chat WebSockets and Twilio media reach
   the runtime public URL through the API-issued ticket/URL flow; API-to-runtime
   control uses its separate server-side token. Bind to `$PORT`, expose `/health`,
   and use one runtime worker. Keep SIM7600 on the Windows edge; the Linux container
   has no modem or local audio device.
2. Keep hosted calls disabled until the existing `ACCEPTANCE.md` gates pass. Admit
   at most one browser call or chat test for 600 seconds after capacity measurement.
   Auto deploy is disabled on both services: the
   `render.yaml` uses `autoDeployTrigger: off`; the release procedure
   requires drain, in-flight completion and operator-controlled deploy. A health
   response proves process liveness, not provider/storage readiness.
3. Put `VOICE_RUNTIME_SPOOL_DIR` and `VOICE_RECORDINGS_DIR` on writable scratch
   paths. On a Render service without a persistent disk these are ephemeral and
   may disappear on restart or deploy. Do not describe the local spool as durable
   across host loss. A persistent Render disk is a paid, single-instance choice;
   make that a separate capacity/cost decision if restart survival is required.
4. Keep Cloudinary and Supabase secrets on the API only. The runtime receives a
   short-lived signed upload grant, never provider secrets. Use deterministic
   org/run/artifact IDs, bounded file sizes, checksums and no overwrite. Cloudinary
   recordings remain `authenticated` and are read through the API. Supabase's
   service key remains server-side and its bucket private; no dashboard storage
   URL or credential is exposed.

## Artifact state and failure handling

| Event | Required outcome |
| --- | --- |
| Call starts | Reserve DB run/lease, check scratch capacity and required storage quota before provider work. |
| Evidence produced | Stream normalized events to the API; retain only the bounded unacknowledged local spool. |
| WAV/log closes | Sanitize logs, hash and measure files, request scoped grants, upload, then call `complete`. |
| Upload fails or is uncertain | Keep source file and `uploading`/incomplete state; reconcile remote identity before retrying. Never mark it available or re-run the call to repair it. |
| Upload completes | API verifies remote identity/checksum and marks available; only then remove scratch copy. |
| Runtime restarts | Fence the old generation, mark the run/evidence/artifact incomplete where needed, do not redial or claim recovered local bytes. |

## Release sequence

1. Reconcile the development and production identity/DB mappings under the local
   ownership plan. Convert Clerk creator/memberships to built-in admin only after
   local owner authorization is validated; keep platform assignment independent.
2. Review `render.yaml` settings and disable runtime auto deploy for the release.
   Verify API/runtime URLs, allowed origins, tokens, region, provider credentials,
   private bucket and authenticated Cloudinary configuration. Run migrations in a
   controlled pre-deploy operation, never at runtime startup.
3. Build and test the exact linux/amd64 image, OpenAPI dashboard client, focused
   auth/runtime/storage contracts and migration head. Deploy with admission off.
4. Test a browser call and a chat conversation only. Hosted Twilio support remains available but live Twilio acceptance is deferred because no account is available. Hosted modem admission remains rejected. Measure
   model-loaded RSS, CPU/event-loop lag, cold start, speech latency, WebSocket
   interruption, ten-minute timeout, shutdown and forced restart. Verify a real
   Cloudinary recording and Supabase diagnostic can be accessed only through an
   authorized API path. Exercise cross-org, expired, duplicate and failed upload
   cases and compare DB artifact status with provider objects.
5. Open admission only after those measurements fit the selected Render plan and
   storage quotas. During later deploys, close admission, drain calls/uploads,
   reconcile uncertain claims, deploy, then reopen. Roll back application code
   only when the database schema and Clerk basic-role compatibility permit it.

## External references

- Render web service and ephemeral disk behavior:
  https://render.com/docs/web-services and https://render.com/docs/disks
- Supabase private/resumable storage behavior:
  https://supabase.com/docs/guides/storage and
  https://supabase.com/docs/guides/storage/uploads/resumable-uploads
- Cloudinary authenticated audio upload:
  https://cloudinary.com/documentation/upload_images and
  https://cloudinary.com/documentation/image_upload_api_reference

The existing `docs/deployment/ACCEPTANCE.md` is the operational gate. This plan
has user authorization for deployment and browser/chat acceptance. Paid resources remain outside this release.
