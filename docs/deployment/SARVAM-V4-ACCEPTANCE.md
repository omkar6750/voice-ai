# Runtime readiness and Sarvam acceptance — October 15, 2026

## Behavior and configuration

`GET /api/v1/runtime-readiness` requires the normal organization login. It returns
starting/ready/busy/unavailable and a three-second retry interval, without an
internal URL, boot ID or credential. Browser and chat startup wait up to two
minutes; cancellation during readiness creates no session or microphone request.
Only GET probes repeat. Uncertain preparation/start responses require reconciliation.

No new mandatory environment variables. Keep one runtime worker, existing
`VOICE_RUNTIME_CONTROL_TOKEN`, `VOICE_RUNTIME_SERVICE_TOKEN`, API runtime URLs,
hosted admission and allowed origins configured as before. No frontend secret.

Opt into `tts.model=bulbul:v4-flash`, choose a persona explicitly and save a new
draft. The editor exposes supported settings and clears incompatible voices on
model changes. V3 remains the default. Malayalam/Odia stay on v3.

The official [voice catalog](https://docs.sarvam.ai/api/api-guides-tutorials/text-to-speech/voices)
was imported with 222 distinct entries. The WebSocket schema's 30-character
minimum is enforced: the guide's suggested 20 returned 422 in a live check.
The adapter uses the live-verified legacy field names rather than conflicting
new guide snippets. No word-aligned playback claims are made.

`stt.realtime.turn_timing=server_only` skips Silero. The explicit draft preset
selects fast streaming and a three-second turn-stop timeout, preserving VAD
thresholds and idle settings. Keepalive is a JSON ping every 30 seconds, never
synthetic caller audio. Missing fields retain existing behavior.

## Small secondary-credential protocol check

Synthetic, non-private speech; one short utterance per case, no load/quota tests.
First-audio timings include local network connection/setup and are single samples.
All successful cases returned a completion event and raw PCM, not a WAV header.

| Model / persona | Rate | First audio | Request ID |
| --- | --- | --- | --- |
| v3 / ritu | 8 kHz | 328 ms | 20261015_f32d6e79-1e0d-4833-95e8-c997cd4b612c |
| v3 / ritu | 16 kHz | 341 ms | 20261015_a71800cb-fed3-4298-b665-5d7205253f79 |
| v4 / simran_en_customer | 8 kHz | 298 ms | 20261015_cb2bc2d7-800f-4ac7-b6af-b7ac6dba6e16 |
| v4 / simran_en_customer | 16 kHz | 299 ms | 20261015_7399b7a1-9709-4863-bca2-63b6484cd919 |
| v4 / ritu_hi_customer | 16 kHz | 409 ms | 20261015_db286b84-75bd-4161-b60e-cc5348f737ec |
| v4 / ritu_mr_narration | 16 kHz | 299 ms | 20261015_d7eb417a-9a5f-4d14-b3f5-b683842f1d9a |
| v4 / ritu_hi_customer, English input | 16 kHz | 375 ms | 20261015_fd64c1c3-24d5-43f6-9627-1fde9f573015 |

The same 16 kHz PCM plus silence produced one final transcript and one speech
start in each STT comparison, with normal client close 1000:

| STT / local VAD | Process CPU time | Peak RSS | Maximum loop lag | Request ID |
| --- | --- | --- | --- | --- |
| v3 realtime / off | 219 ms | 156.7 MB | 27.1 ms | 20261015_27218c87-55a8-4d49-a5b3-92381af9548d |
| v4 / off | 375 ms | 157.6 MB | 26.6 ms | 20261015_108c21c8-6323-4da7-a303-62d7ccefd81b |
| v3 realtime / on | 359 ms | 176.4 MB | 26.8 ms | 20261015_5c89b9d5-e442-4033-bd41-86a0e374cb8d |

These are sequential Windows protocol checks, not full-call benchmarks or CPU
capacity estimates. Model initialization/order and scheduling affect the results.
False interruptions, playback-aware response delay and local-VAD speech timing
in server-only mode are unavailable. The previous production STT failure was not
reproduced; these successes do not establish its cause.

## Automated verification

- 93 focused production-safe unit tests passed.
- 57 development text/runtime tests passed (including overlapping construction coverage).
- 14 rollback-only PostgreSQL chat/browser/phone-dispatch integration tests passed.
- Seven dashboard readiness/model-switch tests passed; TypeScript and Vite builds passed.
- Both Docker images built; packaged runtime reports Pipecat 1.11.0 and catalog count 222.
- Changed Python files pass Ruff; committed files exclude env files, scratch scripts and audio.

## Rollout gates

Deploy backward-compatible API first, runtime second, dashboard last. Confirm
commit identities, authenticated readiness and a warm browser call, then a genuine
Render cold start, readiness cancellation, interruption, goodbye and operator stop.
Publish a separate v4 test version only after those checks. Rollback selects the
existing v3 version. Hosted call acceptance is pending until recorded here.

Private PCM and scratch scripts remain ignored and are not deployment artifacts.

## Hosted rollout record

- API commit `41f0972`, deployment `dep-db8bo71srm7s73e3l2rg`: live; health 200,
  unauthenticated readiness 401 as required.
- Runtime commit `b53373c`, deployment `dep-db8bqem7bikc73b9a2u0`: live; health 200.
- Dashboard commit `c15f810`, deployment `6ad0be146474912f7f02f10b`: ready.
  The subsequent version-selector change enables draft browser acceptance.
- Automatic Render deployments did not queue; fresh-cache deployments were
  requested after checking no new deployment was running. Netlify's earlier
  API-only build was skipped for no dashboard content change.
- The operator explicitly chose `ritu_hi_customer`. Ritu v24 revision 1
  (`5ffb57e9-bcd6-489a-8ae0-c6932374cff6`) is an unpublished draft cloned from
  v23. Only its TTS block differs; all six tool bindings were preserved. V23
  remains active on v3. Server-only timing has not been applied automatically.
- Authenticated operator readiness, warm/cold browser microphone calls,
  interruption, goodbye and operator-stop acceptance remain pending. Repository
  rules prohibit dashboard browser automation; these require the operator's
  logged-in microphone session. Do not publish v24 until they pass.
