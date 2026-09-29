# PLAN-0042 · Secure credentials, recordings and hosted demo

Status: implementation complete; live hosting acceptance remains pending. Supersedes PLAN-0041 hosting placeholders.

## Approved scope

Netlify dashboard/public build assets; one Render FastAPI/Pipecat worker;
Neon application PostgreSQL; authenticated Cloudinary recordings; private
Supabase documents and sanitized diagnostic artifacts. One concurrent call,
browser/Twilio only, maximum300seconds. Hosted calls disabled until memory/latency
verified. No paid provisioning, implicit DB migration, cron, unattended deletion
worker, automatic redial or spending. Preserve protected demo and main callbacks,
async classifiers, fences/termination plus Clerk org creation/home.

## Execution and acceptance

1. Finish authorization audit and both isolated migration histories; merge without
   rebase. See docs/security/tenant-authorization-audit.md for evidence/live gates.
2. Named org credentials with immutable IDs, provider/purpose bindings, write-only
   admin CRUD, versioned replacement, no silent fallback. Per-secret envelopes
   with org/record/provider/purpose AAD, explicit legacy upgrade and server-only
   leases<=60s handshake+300s call+60s cleanup. Delete ciphertext and revoke leases;
   re-add uses a new ID requiring intentional binding repair.
3. Allowlisted logs/sanitized errors: no keys, prompts, transcripts, phone numbers,
   tool payloads, vendor exceptions, SDK wire logs or SQL parameters. Clear browser
   inputs on submission attempts, sign-out, org switch and unmount; no persistence.
4. Validated/checksummed audio, stable org/run/artifact identity, authenticated
   Cloudinary video upload. Store identity not URLs. Current Clerk membership/org
   backend playback private/no-store bytes, temporary Blob cleanup. Admin preview
   snapshots exact inactive org-owned artifacts; actor/org-bound five-minute token;
   durable immediately blocked pending/deleted/failed items; trusted vendor IDs in
   batches<=100; explicit Continue/Retry, absent success, restart/upload-race tests.
   Selected IDs across pages, call/run selections, UTC range and strong all-org
   confirmation. No automatic new expiry; preserve old restrictions. Quota warnings
   and recording-required admission block; recordings deletion retains call history.
5. Deploy config/private storage, generated API contracts, full PostgreSQL tests,
   Ruff/build, cross-org/anonymous/removed-member and tampered/expired preview tests,
   credential lifecycle/mismatch tests, Twilio signature tests and leak sentinels.
   Live Clerk invitations, storage/authentication/deletion, Neon backup/restore,
   Render memory/latency and audible browser/Twilio calls require actual acceptance.

## Disclosures

The zero-cost wrapping root is environment-held, not managed KMS: root compromise
still has shared blast radius. Python memory cleanup is best effort, not assured
physical erasure. App key deletion does not revoke vendor keys or erase backups.
Authorized listeners can save audio. Cloudinary deletion/invalidation is not
instant CDN/backup erasure. Abrupt Render termination can leave incomplete audio
without changing truthful call outcomes.
