# Hosted demo deployment

Status: deployment files only, prepared 2026-09-29. No resources were provisioned,
no migrations were run, and no calls were made. The manifests are not evidence of
working hosted transports or persistence. Parent tracks implementation in
[PLAN-0042](plan/PLAN-0042-secure-hosted-credentials-and-recordings.md); release evidence
belongs in [the acceptance checklist](deployment/ACCEPTANCE.md).

Approved placement:

| Component | Host | Data/access boundary |
| --- | --- | --- |
| Dashboard and public static assets | Netlify | Public built bundle; Clerk session token only in browser memory |
| FastAPI and Pipecat | Render Free Docker web service | One server process and one instance; calls initially disabled |
| Relational state, claims, evidence, pgvector | Neon PostgreSQL | API-only access; durable execution fences |
| Finalized recordings | Cloudinary | Authenticated delivery type; organization-authorized API reads |
| Source documents and sanitized diagnostic files | Private Supabase Storage | Parent-owned server-only adapter; integration subject to acceptance |

Older plans mentioning Supabase recordings are superseded for this hosted design.
Cloudinary owns recordings; Supabase owns private documents and sanitized diagnostics.
No paid resource, worker, cron, scheduler, automatic cleanup/redial, or automatic spend
is authorized. An existing free account's limits must be checked before deployment.
The agent may book a human callback in the configured calendar, but no call is
automatically placed at the booked time; a person must initiate any later call.
Twilio and model APIs can incur usage charges: their credentials and an enabled
transport do not authorize paid calls. Stop at insufficient free allowance.

## Configuration contract for the parent

`render.yaml` contains non-secret defaults and `sync: false` placeholders only.
Pydantic currently ignores unknown environment names, so adding a manifest value
does not implement its gate. Parent must wire and test these before public exposure:

| Environment name | Settings field | Required behavior |
| --- | --- | --- |
| `VOICE_ENV` | `env` | `production`; fail closed for missing production credentials; no dev identity/default keys |
| `VOICE_HOSTED_CALLS_ENABLED` | `hosted_calls_enabled` | `false`; parent gate applies when `env != dev`, before admitting or starting calls |
| `VOICE_MAX_CONCURRENT_CALLS` | `max_concurrent_calls` | `1` across browser and Twilio; database-backed global admission fence |
| `VOICE_CALL_MAX_DURATION_SECONDS` | `call_max_duration_seconds` | `300`; enforce on the server and release safely on timeout |
| `VOICE_ORGANIZATION_CREATION_ENABLED` | `organization_creation_enabled` | `true`; Clerk organization creation is enabled, subject to the one-org claim and live Clerk configuration |
| `VOICE_RECORDINGS_DIR` | `recordings_dir` | `/app/data/recordings`; temporary finalized upload staging only |
| `VOICE_PUBLIC_BASE_URL` | `public_base_url` | Exact public Render HTTPS origin for callback/signature validation |
| `VOICE_CLERK_AUTHORIZED_PARTIES` | `clerk_authorized_parties` | Exact comma-separated approved Netlify origins; also used for CORS; no wildcard |
| `VOICE_DATABASE_URL` | `database_url` | Secret SQLAlchemy asyncpg URL with validated TLS; no localhost default in production |
| `VOICE_INTEGRATION_KEYS` | `integration_keys` | Existing JSON key-ID/Fernet-key map, supplied privately; preserve decryptability |
| `VOICE_INTEGRATION_ACTIVE_KEY` | `integration_active_key` | Existing key ID present in that map; no generated or blank fallback |
| `VOICE_CALLBACK_SLOT_SIGNING_KEY` | `callback_slot_signing_key` | Backend-only high-entropy signing key for callback booking slots |
| `VOICE_RUNTIME_SERVICE_TOKEN` | `runtime_service_token` | Distinct nonempty secret for `X-Voice-Runtime-Token`; never browser auth |
| `CLERK_SECRET_KEY` | `clerk_secret_key` | Backend-only Clerk secret (explicit alias, no `VOICE_` prefix) |
| `CLERK_WEBHOOK_SIGNING_SECRET` | `clerk_webhook_signing_secret` | Nonempty verified webhook secret, explicit alias |
| `VOICE_GOOGLE_CALENDAR_CLIENT_ID` | `google_calendar_client_id` | Platform OAuth client used for user-authorized calendar connections |
| `VOICE_GOOGLE_CALENDAR_CLIENT_SECRET` | `google_calendar_client_secret` | Backend-only OAuth client secret |
| `VOICE_GOOGLE_CALENDAR_REDIRECT_URI` | `google_calendar_redirect_uri` | Exact public Render URL ending in `/api/v1/calendar-integrations/google/callback` |
| `VOICE_CLOUDINARY_CLOUD_NAME` | `cloudinary_cloud_name` | Matching recording account |
| `VOICE_CLOUDINARY_API_KEY` | `cloudinary_api_key` | Backend-only authenticated upload/read/delete credential |
| `VOICE_CLOUDINARY_API_SECRET` | `cloudinary_api_secret` | Backend-only secret; no public download URL persistence |
| `VOICE_SUPABASE_URL` | `supabase_url` | Existing Supabase project's HTTPS origin |
| `VOICE_SUPABASE_SERVICE_KEY` | `supabase_service_key` | Privileged backend-only storage credential |
| `VOICE_SUPABASE_PRIVATE_BUCKET` | `supabase_private_bucket` | `voice-private`; private documents and sanitized pipeline_log objects |
| `VOICE_RECORDING_QUOTA_BYTES` | `recording_quota_bytes` | Optional explicit verified byte allowance; no default in Blueprint; unknown quota blocks recording-required calls |

Parent admission must allow only browser/Twilio when `env != dev`; no fabricated
transport/automation env flags are provided. Parent constrains `max_concurrent_calls`
to at most 1 and `call_max_duration_seconds` to at most 300. No scheduler or worker
is started by these manifests. Existing per-workspace callback settings must also
remain off. A flag never substitutes
for durable DB fencing, per-operation organization authorization, or runtime enforcement.
Keep the existing integration keyring names until the credential owner supplies a
reviewed replacement/rotation plan. Callback signing must also use a configured
backend secret if that feature is enabled; no new weak signing default is supplied.

Do not add STT/LLM/TTS/embedding provider keys to Render's environment or Netlify.
Hosted provider resolution must use the credential owner's approved encrypted
organization credential path and fail closed. The current runtime's environment-key
path is a release blocker until that integration is complete. No secrets belong in
build arguments, Docker layers, dotenv copies, frontend settings, diagnostics, or logs.
`sync: false` prompts on initial Blueprint creation; later additions require a manual
Dashboard value. It does not rotate a key. See [Render env wiring](https://render.com/docs/blueprint-spec#environment-variables).

## Build and release

Docker uses Python 3.12, uv 0.9.17, `uv lock --check` and frozen production installs
from `uv.lock`, followed by a non-editable project install. Builder and runner share
the same Python image family. The runner has CA certificates, libsndfile, PortAudio
and libgomp, runs UID/GID 10001, and launches Uvicorn on `0.0.0.0:$PORT` with one
worker. No startup/install step migrates or invokes the protected demo. The default
deny Docker context includes only Python build inputs. Image tags pin a version/family,
not an immutable digest; record resolved digests in release evidence. These choices
follow [uv's Docker guidance](https://docs.astral.sh/uv/guides/integration/docker/).

After implementation gates pass, validate locally from the repository root:

```powershell
uv run --no-sync pytest tests/unit/test_deployment_config.py
uv run --no-sync ruff check tests/unit/test_deployment_config.py
docker build --check .
docker build --platform linux/amd64 -t voice-ai-demo:review .
```

An actual image build/start is a separate acceptance check. Native imports, ONNX/model
loading, RSS and audio timing must be measured inside that image on Render. Static
tests do not validate calls or prove that a model fits available memory.

Render CLI v2.7+ can validate using `render blueprints validate` (discover local help
first); alternatively validate against [the official JSON schema](https://render.com/schema/render.yaml.json).
The Blueprint defines one free web service, previews off, and automatic deployments
off. Free services are single-instance; `numInstances` is omitted to avoid unsupported
scaling configuration. Do not add a Render database, disk, autoscaling or predeploy
migration command. The operator must verify the repository/ref before manually
applying the Blueprint; these files authorize neither provisioning nor pushing.

For Neon, use the existing SQLAlchemy/Alembic architecture. Prefer the pooled endpoint
for short application transactions; use a direct connection for reviewed operator-run
migrations and backups. Pooling is transaction-scoped: ownership fences and tenant
context must be transactional, not session advisory locks or persistent `SET` state.
Verify asyncpg's URL/TLS handling: use the `postgresql+asyncpg` driver and its supported
TLS options/verified SSL context; do not blindly copy libpq-only `sslmode` or
`channel_binding` keyword arguments. Test CA and hostname verification and pool
reconnect before release. See [Neon pooling](https://neon.com/docs/connect/connection-pooling)
and [secure connections](https://neon.com/docs/connect/connect-securely).

Migrations are a deliberate operator action from a trusted checkout, with an existing
direct Neon URL injected privately into `VOICE_DATABASE_URL`, followed by
`uv run alembic upgrade head` and `uv run alembic current`. Never place them in Docker
CMD, Render startup, predeploy, Netlify build, or scheduled work. Capture the migration
revision, pgvector availability, preservation checks and restore evidence first.

Netlify reads root `netlify.toml`, builds in `apps/dashboard` with Node 24, and publishes
only `dist`. For local Vite use, copy `apps/dashboard/.env.example` to `.env.local` and
set `VITE_CLERK_PUBLISHABLE_KEY` plus `VITE_API_ORIGIN`; optional Clerk routing variables
control the sign-in, sign-up, organization creation, invitation, and profile paths.
The dashboard reads only public Vite variables and never sources its publishable key from
the backend `.env`. For hosted builds set the public Clerk variables and `VITE_API_ORIGIN`
in Netlify's build environment; the API origin must be HTTPS
without credentials or a path. The deployment
guard rejects other `VITE_` names and Vite production dotenv files without reading
them, and gives its npm/Vite processes only public keys and basic OS variables.
Netlify's preliminary install uses `NPM_FLAGS` to preserve the reviewed lock and skip
scripts; the guard then runs the authoritative `npm ci` and existing build with its
filtered environment. Keep Netlify's own environment free of server credentials.
The SPA rewrite is non-forced so real assets win; no API/media
proxy, functions, secrets, recordings, documents or diagnostics are published. All
routes receive browser/CDN `no-store`. API/media responses require their own `no-store`
headers on Render; Netlify headers cannot cover another origin. See [Netlify build
configuration](https://docs.netlify.com/build/configure-builds/file-based-configuration/),
[Node versions](https://docs.netlify.com/build/configure-builds/manage-dependencies/),
and [SPA rewrites](https://docs.netlify.com/manage/routing/redirects/rewrites-proxies/).
Disable unwanted branch/preview builds and automatic build triggers in Netlify's UI;
the manifest cannot configure every account setting. Keep usage inside existing free
allowances with automatic credit purchases disabled.

## Storage integration requirements

The concurrent recording owner is adding a Cloudinary adapter; its presence alone
does not prove runtime upload, read authorization, dependency locking or retention
integration. Require `resource_type=video`, `type=authenticated` for WAV originals
and derived media, trusted DB identities, checksum/size checks and no overwrite on
replay. Serve through the organization-authorized API, with a time-limited backend
download and no-store response. Ordinary signed delivery URLs do not by themselves
prove expiry; the adapter's `private_download_url` supports `expires_at`. Validate
unsigned original/derived access denial and access after removal. See [Cloudinary
access control](https://cloudinary.com/documentation/control_access_to_media).

The parent-owned `services/private_storage.py` now provides a Storage REST adapter
and diagnostic sanitization. These deployment files do not implement or validate
its application integration. Do not advertise working persistence until it passes
acceptance. Use the existing private `voice-private` bucket with explicit size/MIME
limits and distinct document/diagnostic prefixes. The bucket name is
operator configuration, not public browser settings. Private downloads require
authorized retrieval or short-lived signed access; public buckets bypass read
controls. See [bucket access](https://supabase.com/docs/guides/storage/buckets/fundamentals).

Choose server-only Supabase Storage REST/SDK access using a secret key (`sb_secret_...`)
kept on Render; legacy `service_role` is compatibility only. Configure either through
`VOICE_SUPABASE_SERVICE_KEY`, with format-specific client handling. Modern secret keys
belong in `apikey`; they are not JWT bearer tokens. The inspected adapter sends both
headers, so modern-key compatibility must be tested or adjusted by its owner before
release. Both privileged
forms bypass RLS, so the API must authorize Clerk organization membership and resolve
the DB-owned object identity before upload, read, list, sign or delete. Keep anonymous
and browser access denied; an `authenticated` policy alone does not establish
organization ownership. Do not assume Clerk subjects are UUID `auth.uid()` values.
See [Supabase key semantics](https://supabase.com/docs/guides/getting-started/api-keys)
and [Storage access control](https://supabase.com/docs/guides/storage/security/access-control).

Server-created objects may have no `owner_id`; that column neither supplies tenancy
nor access checks. Keep authoritative organization, source/run, bucket/key, MIME,
bytes, checksum, expiry and deletion status in Neon, with opaque trusted object
identities. See [Storage ownership](https://supabase.com/docs/guides/storage/security/ownership).
The adapter must stream bounded data, reject arbitrary URLs/paths, preserve active
chunks after ingestion failure, fence stale/deleted-source work, reconcile uncertain
uploads without overwrites, and explicitly delete remote objects through the Storage
API. Direct SQL metadata deletion does not implement file deletion. A signed URL is
a bearer capability until expiry and must never be logged or stored as object identity.
Prefer the API proxy for revocation-sensitive documents and diagnostics.

Sanitize diagnostics before local persistence and upload. Exclude credentials,
Authorization/cookies, signed URLs, raw provider payloads and unapproved conversation
content; retain only approved typed operational facts. Add negative redaction tests
and cross-org upload/read/list/delete tests. No scheduled expiry job is included:
expired objects become inaccessible through API policy, and an operator explicitly
deletes eligible objects, recording remote outcomes/tombstones. Do not claim physical
expiry deletion or a retention SLA until those paths pass acceptance.

The [Supabase changelog](https://supabase.com/changelog) was checked for relevant
breaking changes. Its [managed schema restriction](https://supabase.com/changelog/34270-restricting-access-on-auth-storage-and-realtime-schemas-on-april-21-2025)
reinforces using supported Storage APIs rather than modifying managed schema objects.
This design adds no Supabase Auth, database tables, Realtime or migrations.

## Call gate and deployment interruption

Calls remain disabled until the complete acceptance checklist passes on actual Render.
Free Render spins down after inactivity, can restart, and loses local files on
restart/redeploy. No persistent disk or durable local spool is available; uploaded
remote artifacts and DB evidence are durable, unfinished local data is not. Failed
upload/delivery must remain explicitly incomplete. Free usage can suspend services,
and supplementary usage may be billed when a payment method is present. Disable
automatic spending and stop before exhaustion. See [Render Free constraints](https://render.com/docs/free).

One Uvicorn process preserves local ownership, but old/new processes can overlap during
a deployment. Require durable PostgreSQL admission/claim fencing before provider/media
side effects; uncertain attempts stay reserved until explicit reconciliation. Every
browser/Twilio session shares the single-call cap, and has a 300-second server deadline.
No fallback to local SIM7600 or automatically retried telephone attempt is permitted.

Before every manual release or rollback: close durable admission, keep hosted calls
disabled, verify no new leases can be admitted, wait for the active call and evidence
upload to finish, and verify zero live/uncertain claims before deploying. A live run
needs a DB-backed drain decision; changing a Render env var can itself redeploy and
is not a safe drain mechanism. If the drain interface is absent, keep calls disabled.
Render allows at most 300 seconds of shutdown delay; the image's Uvicorn timeout is
285 seconds. Neither setting guarantees five-minute call completion on redeploy.
See [Render deploy/shutdown behavior](https://render.com/docs/deploys#graceful-shutdown).
After restart reconcile incomplete evidence and external state without redial, test
health/auth/storage, then reopen admission only after operator acceptance.
