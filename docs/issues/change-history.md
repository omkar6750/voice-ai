# Change history

Source: non-merge commits reachable from `42f7b10`, reviewed October 15, 2026. Subjects are historical descriptions, not fresh acceptance claims. Related issue records explain known failures; formatting and initial feature commits remain visible here without invented incident causes.

| Commit | Date | Recorded change | Areas changed |
|---|---|---|---|
| `42f7b10` | 2026-10-10 | fix: isolate voicemail context and make call shutdown reliable | apps/api/voice_api, apps/dashboard/src, apps/runtime/voice_runner, docs, packages/voice_runtime/voice_runtime, packages/voice_shared/voice_shared, tests |
| `612a6ab` | 2026-10-09 | Add capabilities and anonymized run gallery to landing | apps/dashboard/public, apps/dashboard/src |
| `1f00833` | 2026-10-09 | feat: retain modem URCs and diagnose call outcomes | DECISIONS.md, MEMORY.md, apps/api/voice_api, apps/dashboard/src, apps/runtime/voice_runner, docs, packages/voice_runtime/voice_runtime, tests |
| `28d51aa` | 2026-10-09 | Add public voice AI landing page with Clerk-gated dashboard entry | apps/dashboard/index.html, apps/dashboard/public, apps/dashboard/src |
| `1020fe9` | 2026-10-09 | Fix terminal rendering and expose recorded node transitions | apps/dashboard/scripts, apps/dashboard/src, packages/voice_runtime/voice_runtime, packages/voice_shared/voice_shared, tests |
| `745945d` | 2026-10-09 | Use one uniform shade for fallback prompt highlights | apps/dashboard/scripts, apps/dashboard/src |
| `a51027b` | 2026-10-09 | Render fallback prompts as one priority gradient highlight | apps/dashboard/scripts, apps/dashboard/src |
| `86d99b0` | 2026-10-09 | Add conversation fact defaults and node-entry prompt fallbacks | DECISIONS.md, MEMORY.md, apps/api/voice_api, apps/dashboard/scripts, apps/dashboard/src, contracts, docs, packages/voice_runtime/voice_runtime, packages/voice_shared/voice_shared, tests |
| `270cef0` | 2026-10-09 | Snapshot current workspace baseline for isolated fact feature | .claude, .gemini, .gitignore, DECISIONS.md, MEMORY.md, apps/api/.env.example, apps/api/voice_api, apps/dashboard/src, apps/runtime/voice_runner, docs, migrations, packages/voice_runtime/voice_runtime, packages/voice_shared/voice_shared, pyproject.toml, scripts, tests, uv.lock |
| `b0276c7` | 2026-10-05 | Allow local dashboard origin for Clerk auth | apps/api/.env.example, apps/api/voice_api, tests |
| `7876b67` | 2026-10-05 | Add Sarvam realtime STT with server endpointing | apps/dashboard/src, packages/voice_runtime/voice_runtime, tests |
| `942dc56` | 2026-10-05 | Expose Saaras v4 and harden legacy STT input | apps/dashboard/src, docs, packages/voice_runtime/voice_runtime, tests |
| `c4c6f2c` | 2026-10-05 | Allow cloning legacy agents before repairing opening tasks | apps/api/voice_api, tests |
| `4330be4` | 2026-10-05 | Require configured opening tasks and preserve fallback node instructions | apps/api/voice_api, apps/dashboard/scripts, apps/dashboard/src, apps/runtime/voice_runner, docs, packages/voice_runtime/voice_runtime, tests |
| `5cbd1b6` | 2026-10-04 | Report sanitized runtime startup configuration failures | apps/runtime/voice_runner, tests |
| `310c560` | 2026-10-04 | Retain hosted Twilio support and defer live Twilio acceptance | apps/api/voice_api, apps/runtime/voice_runner, docs, tests |
| `47c1a32` | 2026-10-04 | Activate hosted browser and chat runtime with controlled releases | apps/api/voice_api, apps/runtime/voice_runner, docs, render.yaml, tests |
| `b172ca2` | 2026-10-04 | Record Clerk ownership cutover prerequisites | docs |
| `918250e` | 2026-10-04 | Keep platform context available during membership lookup outages | apps/api/voice_api |
| `45b4798` | 2026-10-04 | Use local ownership with Clerk basic roles and plan hosted runtime | apps/api/voice_api, apps/dashboard/src, docs, tests |
| `2ddf88a` | 2026-10-04 | Integrate read performance, diagnostics, and runtime fixes | DECISIONS.md, MEMORY.md, apps/api/.env.example, apps/api/voice_api, apps/dashboard/scripts, apps/dashboard/src, apps/runtime/.env.example, apps/runtime/voice_runner, docs, migrations, packages/voice_runtime/voice_runtime, packages/voice_shared/voice_shared, scripts, tests |
| `4fb2f66` | 2026-10-04 | Add configurable WhatsApp composer and evidence views | apps/api/voice_api, apps/dashboard/src, apps/runtime/voice_runner, docs, packages/voice_runtime/voice_runtime, tests |
| `48eb4b3` | 2026-10-02 | Separate voice runtime and add text testing, flow editor and Ritu configuration | .dockerignore, DECISIONS.md, Dockerfile, Dockerfile.runtime, MEMORY.md, apps/api/.env.example, apps/api/voice_api, apps/dashboard/.env.example, apps/dashboard/package-lock.json, apps/dashboard/package.json, apps/dashboard/scripts, apps/dashboard/src, apps/runtime/.env.example, apps/runtime/voice_runner, docs, migrations, packages/voice_runtime/voice_runtime, packages/voice_shared/voice_shared, pyproject.toml, render.yaml, scripts, tests, uv.lock |
| `27b2d81` | 2026-10-02 | Add Isoquant Pipecat provider and local Gnani documentation | apps/api/voice_api, apps/dashboard/src, docs, packages/voice_runtime/voice_runtime, tests |
| `240f639` | 2026-10-02 | feat: redesign tools version authoring workspace | apps/api/voice_api, apps/dashboard/package-lock.json, apps/dashboard/package.json, apps/dashboard/scripts, apps/dashboard/src, docs, tests |
| `cbc60fd` | 2026-10-01 | feat: improve runtime providers and diagnostics | apps/api/.env.example, apps/api/voice_api, apps/dashboard/src, docs, packages/voice_runtime/voice_runtime, tests |
| `dd6a579` | 2026-10-01 | fix: make callback slots speech friendly | apps/api/voice_api, packages/voice_runtime/voice_runtime, tests |
| `d3c8b6d` | 2026-10-01 | chore: enable Render auto-deploys | render.yaml |
| `a814d61` | 2026-10-01 | feat: harden callback scheduling and calendar testing | apps/api/voice_api, apps/dashboard/src, docs, packages/voice_runtime/voice_runtime, tests |
| `5f881bb` | 2026-09-30 | Support ten-minute hosted calls | apps/api/voice_api, docs, packages/voice_runtime/voice_runtime, render.yaml, tests |
| `83fd2a7` | 2026-09-30 | fix(dashboard): recover from transient Clerk 401s | apps/dashboard/src |
| `ad168bc` | 2026-09-30 | Use unmistakably synthetic Twilio test identifiers | tests |
| `4ce4ddf` | 2026-09-30 | Verify Render and Netlify deployment packaging | .dockerignore, docs, render.yaml, tests |
| `2219eea` | 2026-09-30 | Complete provider credential and model configuration flows | apps/api/.env.example, apps/api/voice_api, apps/dashboard/src, packages/voice_runtime/voice_runtime, tests |
| `d15c382` | 2026-09-30 | feat(clerk): complete org onboarding and runtime boundaries | .env.example, AGENTS.md, CLAUDE.md, Dockerfile, README.md, apps/api/.env.example, apps/api/voice_api, apps/dashboard/.env.example, apps/dashboard/src, apps/dashboard/vite.config.ts, docs, netlify.toml, packages/voice_runtime/voice_runtime, render.yaml, scripts, tests |
| `5aba9c0` | 2026-09-30 | feat(openrouter): add org-bound provider integration | apps/api/voice_api, apps/dashboard/src, packages/voice_runtime/voice_runtime, pyproject.toml, tests, uv.lock |
| `4f90639` | 2026-09-30 | perf(dashboard): avoid blocking on app context | apps/dashboard/src |
| `d317e43` | 2026-09-30 | fix platform admin endpoint access | apps/api/voice_api, apps/dashboard/package.json, apps/dashboard/src, tests |
| `0fd8698` | 2026-09-30 | perf(dashboard): add query caching and lazy loading | .agents, apps/dashboard/package-lock.json, apps/dashboard/package.json, apps/dashboard/src |
| `6732bdd` | 2026-09-29 | Implement secure org credentials and recordings | .dockerignore, Dockerfile, apps/api/voice_api, apps/dashboard/src, docs, migrations, netlify.toml, packages/voice_runtime/voice_runtime, pyproject.toml, render.yaml, scripts, tests, uv.lock |
| `c700103` | 2026-09-29 | Allow dev config cleanup for published versions | migrations |
| `76f6c8c` | 2026-09-29 | Implement callback routing and async classifier outcomes | DECISIONS.md, apps/api/voice_api, apps/dashboard/src, docs, migrations, packages/voice_runtime/voice_runtime, tests |
| `6606791` | 2026-09-29 | Complete Clerk organization runtime boundaries | .env.example, apps/api/voice_api, apps/dashboard/src, migrations, packages/voice_runtime/voice_runtime |
| `fdd7f53` | 2026-09-29 | Enable Clerk organization creation | .env.example, apps/api/voice_api |
| `b2af9be` | 2026-09-29 | Complete Clerk organization tenancy foundation | .env.example, .gitignore, DECISIONS.md, apps/api/voice_api, apps/dashboard/package-lock.json, apps/dashboard/package.json, apps/dashboard/src, apps/dashboard/vite.config.ts, docs, migrations, packages/voice_runtime/voice_runtime, pyproject.toml, tests, uv.lock |
| `050edb1` | 2026-09-29 | fix: harden callback scheduling and document runtime plans | apps/api/voice_api, docs, packages/voice_runtime/voice_runtime, scripts, tests |
| `f4c355b` | 2026-09-29 | Align PostgreSQL schema with ORM models | migrations |
| `3803ad5` | 2026-09-29 | Make calendar and classifier migrations safe on fresh databases | migrations |
| `da0a9e3` | 2026-09-29 | Support validated end-call lifecycle actions | apps/api/voice_api, docs, packages/voice_runtime/voice_runtime, tests |
| `fb2ebea` | 2026-09-29 | Fence expired browser sessions before WebRTC startup | apps/api/voice_api, tests |
| `7570b65` | 2026-09-29 | Close browser calls on Pipecat peer-left signal | apps/dashboard/src, apps/dashboard/tests |
| `4c91682` | 2026-09-29 | Document Twilio lifecycle guarantees and offline verification limits | DECISIONS.md, docs |
| `babe259` | 2026-09-29 | Verify managed Twilio codecs match stock across rates | tests |
| `5ca9f3d` | 2026-09-29 | Reject invalid Twilio dispatch settings before queueing | apps/api/voice_api, tests |
| `9b4beba` | 2026-09-29 | Wire authenticated Twilio streams through truthful run finalization | apps/api/voice_api, tests |
| `99517ed` | 2026-09-29 | Fence outbound Twilio attempts and preserve callback races | apps/api/voice_api, packages/voice_runtime/voice_runtime, tests |
| `2e87acf` | 2026-09-29 | Fence Twilio media claims and retain callback identity | apps/api/voice_api, tests |
| `c495d48` | 2026-09-29 | Validate Twilio signatures and bounded stream handshakes | packages/voice_runtime/voice_runtime, tests |
| `e1c8cf0` | 2026-09-29 | Own Twilio playback drain and verified hangup once | packages/voice_runtime/voice_runtime, tests |
| `23677a3` | 2026-09-29 | Order Twilio callbacks without inferring Run success | apps/api/voice_api, tests |
| `55430fa` | 2026-09-29 | Add bounded sanitized Twilio call REST adapter | packages/voice_runtime/voice_runtime, tests |
| `d2eafe1` | 2026-09-29 | docs: record browser lifecycle fixes and verification gates | .gitignore, docs |
| `aa6b18e` | 2026-09-29 | fix: handle browser peer termination without stale call state | apps/dashboard/src, apps/dashboard/tests |
| `e34a9dd` | 2026-09-29 | fix: make native host cleanup idempotent and retain primary failures | packages/voice_runtime/voice_runtime, tests |
| `e6206d8` | 2026-09-29 | fix: report browser artifact registration failures separately | apps/api/voice_api, tests |
| `53c4b36` | 2026-09-29 | fix: persist truthful browser termination outcomes | apps/api/voice_api, packages/voice_runtime/voice_runtime, tests |
| `338f627` | 2026-09-29 | fix: join conversation tasks when execution supervisor is cancelled | packages/voice_runtime/voice_runtime, tests |
| `bf09392` | 2026-09-29 | style: normalize browser cleanup test imports | tests |
| `3471e89` | 2026-09-29 | fix: close browser resources once even after cleanup failure | apps/api/voice_api, tests |
| `48c8917` | 2026-09-29 | docs: record terminal lifecycle fixes and remaining transport verification | docs |
| `4729a1b` | 2026-09-29 | fix: bound graceful pipeline shutdown with monotonic deadlines | packages/voice_runtime/voice_runtime, tests |
| `b7c5d73` | 2026-09-29 | fix: keep artifact failure separate from call outcome | packages/voice_runtime/voice_runtime, tests |
| `713ed93` | 2026-09-29 | fix: close terminal nodes through ordered Pipecat output actions | packages/voice_runtime/voice_runtime, tests |
| `e249fa8` | 2026-09-29 | fix: record flow visits before dispatching node responses | packages/voice_runtime/voice_runtime, tests |
| `112aa3c` | 2026-09-29 | docs: record reviewed runtime slices and debugging checks | docs |
| `d13412b` | 2026-09-29 | fix: report native termination outcomes without treating drops as success | packages/voice_runtime/voice_runtime, tests |
| `daa59ed` | 2026-09-29 | refactor: isolate flow transitions and ordered tool evidence | packages/voice_runtime/voice_runtime |
| `2c2eaa4` | 2026-09-29 | fix: retain termination cause and report failed native cleanup truthfully | packages/voice_runtime/voice_runtime, tests |
| `c91ade3` | 2026-09-29 | refactor: isolate speech construction without changing provider settings | packages/voice_runtime/voice_runtime, tests |
| `e57b57d` | 2026-09-29 | test: verify resolved speech settings reach provider constructors | tests |
| `408ee31` | 2026-09-29 | fix: deliver end-call tool result before graceful shutdown | packages/voice_runtime/voice_runtime, tests |
| `4626942` | 2026-09-29 | fix: preserve runtime history during uncertain-call reconciliation | apps/api/voice_api, tests |
| `b56c42a` | 2026-09-29 | fix: reject unsuccessful callback responses without leaking details | packages/voice_runtime/voice_runtime, tests |
| `7ab49ad` | 2026-09-28 | feat: add provider-neutral usage and immutable cost calculations | packages/voice_runtime/voice_runtime, tests |
| `8283d40` | 2026-09-28 | feat: model termination intent and observed call outcome | packages/voice_runtime/voice_runtime, tests |
| `8f3b943` | 2026-09-28 | test: isolate calendar settings and match async session mocks | .gitignore, tests |
| `e77a0b4` | 2026-09-28 | feat: show WhatsApp delivery receipts in run timeline | DECISIONS.md, apps/api/voice_api, apps/dashboard/src, docs, packages/voice_runtime/voice_runtime, tests |
| `bcb8d67` | 2026-09-28 | feat: use Meta-hosted WhatsApp template media | .env.example, DECISIONS.md, apps/api/voice_api, apps/dashboard/src, docs, migrations, packages/voice_runtime/voice_runtime, scripts, tests |
| `c42c9f5` | 2026-09-28 | feat: harden runtime evidence and classifier behavior | DECISIONS.md, apps/api/voice_api, apps/dashboard/src, docs, packages/voice_runtime/voice_runtime, scripts, tests |
| `b9a941d` | 2026-09-28 | feat: complete classifier and tool authoring work | apps/api/voice_api, apps/dashboard/src, docs, migrations, packages/voice_runtime/voice_runtime, tests |
| `0ec6ed1` | 2026-09-28 | fix: use workspace schema for workspace settings | apps/api/voice_api, tests |
| `81fdef1` | 2026-09-28 | Replace operator bearer token with Clerk owner and runtime service auth | .env.example, AGENTS.md, apps/api/voice_api, apps/dashboard/src, docs, packages/voice_runtime/voice_runtime, scripts, tests |
| `7ebfc22` | 2026-09-28 | Add Clerk identity foundation and B2B tenancy architecture | .env.example, apps/api/voice_api, apps/dashboard/package-lock.json, apps/dashboard/package.json, apps/dashboard/src, apps/dashboard/vite.config.ts, docs, pyproject.toml, tests, uv.lock |
| `0a7a446` | 2026-09-27 | Wire agent call controls, scoped knowledge, Cartesia, and usage evidence | apps/api/voice_api, apps/dashboard/src, migrations, packages/voice_runtime/voice_runtime, scripts, tests |
| `e7eac0d` | 2026-09-27 | Document agent workstreams and expose provider-neutral summarizer draft | apps/dashboard/src, docs, tests |
| `d370e85` | 2026-09-27 | Implement verbatim opening and context role boundary | apps/dashboard/src, docs, packages/voice_runtime/voice_runtime, tests |
| `02976bf` | 2026-09-27 | feat: implement plans 0008-0016 and endpoint probing | DECISIONS.md, apps/api/voice_api, apps/dashboard/src, docs, migrations, packages/voice_runtime/voice_runtime, tests |
| `9e494ab` | 2026-09-27 | feat(classifier): record classifier context results | apps/api/voice_api, packages/voice_runtime/voice_runtime, tests |
| `925cdbf` | 2026-09-26 | feat(browser-sessions): add browser test call contact context and modal | apps/api/voice_api, apps/dashboard/src, docs, migrations, packages/voice_runtime/voice_runtime, pyproject.toml, tests, uv.lock |
| `938f707` | 2026-09-26 | fix(contracts): allow role_prompt and context_strategy in FlowNodeConfig | packages/voice_runtime/voice_runtime, tests |
| `cfd3019` | 2026-09-26 | feat(knowledge): fix embedding search 500, auto-resolve kb tools, and add chunks inspector UI | apps/api/voice_api, apps/dashboard/src |
| `eb1c8ae` | 2026-09-26 | feat(telephony): complete twilio integration and strict signature validation | apps/api/voice_api, apps/dashboard/src, docs, migrations, packages/voice_runtime/voice_runtime, pyproject.toml, tests, uv.lock |
| `9c5874a` | 2026-09-26 | feat(tools,agents,integrations): add impact-checked deletion flows, WhatsApp disconnect, and direct messaging 24h window | .agents, .claude, .codex, .cursor, .gemini, .github, .mcp.json, .tessl, CLAUDE.md, apps/api/voice_api, apps/dashboard/src, migrations, packages/voice_runtime/voice_runtime, skills-lock.json, tessl.json, tests |
| `40fdf09` | 2026-09-26 | feat(calendar,flows): add Google Calendar callback scheduling and flow context controls | .env.example, .gitignore, apps/api/voice_api, apps/dashboard/src, apps/dashboard/vite.config.ts, migrations, packages/voice_runtime/voice_runtime, pyproject.toml, tests, uv.lock |
| `3c924db` | 2026-09-25 | feat(dashboard): integrate rebuild forms and operator workflows | apps/api/voice_api, apps/dashboard/src, docs, packages/voice_runtime/voice_runtime, pyproject.toml, scripts, tests, uv.lock |
| `7727740` | 2026-09-25 | refactor(api): remove obsolete root forwarding shims | apps/api/voice_api, tests |
| `1a10e33` | 2026-09-25 | feat(dashboard): rebuild operator pages from runs baseline | apps/dashboard/src, docs |
| `41bd77f` | 2026-09-24 | feat(dashboard): add telugu language support, unredacted phone display, pipeline islands UI, and dynamic flow node controls | apps/dashboard/src |
| `5a88422` | 2026-09-24 | feat(dashboard): add strongly-typed client DTOs, full agent version editor, and whatsapp integration controls | apps/dashboard/src |
| `ccdcc26` | 2026-09-24 | feat(dashboard): complete CRUD for agents, contacts, and knowledge sources with semantic search fixes | apps/api/voice_api, apps/dashboard/src |
| `44675ff` | 2026-09-24 | fix(dashboard): align vault secret payload key with api schema | apps/dashboard/src |
| `35e734d` | 2026-09-24 | feat(dashboard): implement full surface pages per RFC-0004 through RFC-0012 and global quick dialer | AGENTS.md, apps/api/voice_api, apps/dashboard/src |
| `2b50710` | 2026-09-24 | feat(runtime): connect live whatsapp tool adapter, flexible transitions, and simplify run inspector | apps/api/voice_api, apps/dashboard/src, packages/voice_runtime/voice_runtime, scripts, tests |
| `e674583` | 2026-09-24 | Build Runs-first shadcn dashboard | README.md, apps/api/voice_api, apps/dashboard/package-lock.json, apps/dashboard/package.json, apps/dashboard/src, apps/dashboard/vite.config.ts, docs, tests |
| `defa3aa` | 2026-09-24 | Set up Tailwind v4 and shadcn dashboard primitives | AGENTS.md, apps/api/voice_api, apps/dashboard/components.json, apps/dashboard/package-lock.json, apps/dashboard/package.json, apps/dashboard/postcss.config.cjs, apps/dashboard/src, apps/dashboard/tailwind.config.cjs, apps/dashboard/tsconfig.app.json, apps/dashboard/tsconfig.json, apps/dashboard/vite.config.ts, docs |
| `f9a6bb0` | 2026-09-24 | Build Tailwind dashboard foundation and update UI RFCs | AGENTS.md, apps/api/voice_api, apps/dashboard/package-lock.json, apps/dashboard/package.json, apps/dashboard/postcss.config.cjs, apps/dashboard/src, apps/dashboard/tailwind.config.cjs, docs, tests |
| `94d9141` | 2026-09-23 | feat(telephony): dynamic agent resolution, call limits, and Neotribe campaign configuration | apps/api/voice_api, scripts |
| `daa857b` | 2026-09-23 | feat(calls): configure 600s in database agent version, remove env var from demo_call, and add run/call inspection endpoints | apps/api/voice_api, scripts |
| `ab70267` | 2026-09-23 | feat(telephony): allow configuring MAX_CALL_SECONDS via VOICE_MAX_CALL_SECONDS | scripts |
| `5daf824` | 2026-09-23 | feat(calls): add manual call dispatch endpoint and direct dispatch parameter | apps/api/voice_api |
| `ffb815c` | 2026-09-23 | fix(config): resolve repository root .env file from any working directory | apps/api/voice_api |
| `5ee6ea1` | 2026-09-23 | feat(seed): add seed script for demo SDR agent, tools, knowledge, and vault credentials | .gitignore, apps/api/voice_api, docs, scripts |
| `d24e9cb` | 2026-09-23 | refactor(api): restructure FastAPI application into layered core, db, schemas, api, and services architecture | AGENTS.md, apps/api/voice_api, migrations, tests |
| `b7c27cf` | 2026-09-23 | refactor: keep standalone demo settings in demo script | AGENTS.md, MEMORY.md, docs, packages/voice_runtime/voice_runtime, scripts, tests |
| `c3ee9b8` | 2026-09-23 | refactor: remove obsolete runtime path and document remaining work | .env.example, AGENTS.md, MEMORY.md, README.md, apps/api/voice_api, docs, packages/voice_runtime/voice_runtime, pyproject.toml, tests |
| `0a04df0` | 2026-09-23 | fix: stream runtime evidence and handle storage failures safely | MEMORY.md, docs, packages/voice_runtime/voice_runtime, tests |
| `a1671d2` | 2026-09-23 | feat: add execution safety analysis history and artifact retention | .gitignore, MEMORY.md, README.md, apps/api/voice_api, apps/dashboard/src, docs, migrations, packages/voice_runtime/voice_runtime, pyproject.toml, scripts, tests, uv.lock |
| `3ed7106` | 2026-09-23 | feat: enforce publication integrity and persist run evidence | .gitignore, DECISIONS.md, MEMORY.md, README.md, apps/api/voice_api, docs, migrations, packages/voice_runtime/voice_runtime, tests |
| `69523d2` | 2026-09-23 | feat: add configurable voice runtime foundation | .env.example, AGENTS.md, MEMORY.md, apps/api/voice_api, apps/dashboard/package-lock.json, apps/dashboard/package.json, apps/dashboard/scripts, apps/dashboard/src, apps/dashboard/vite.config.ts, docker-compose.yml, docs, migrations, packages/voice_runtime/voice_runtime, pyproject.toml, uv.lock |
| `42dd1c7` | 2026-09-22 | Implement validated SIM7600 voice runtime | .env.example, .gitignore, AGENTS.md, DECISIONS.md, README.md, apps/api/voice_api, docs, packages/voice_runtime/voice_runtime, pyproject.toml, scripts, tests, uv.lock |
| `693f57f` | 2026-09-21 | Initialize voice agent foundation |  |
