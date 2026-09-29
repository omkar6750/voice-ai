---
title: Dashboard configuration controls against runtime
status: Audit
date: 2026-09-29
related: [RFC-0003, RFC-0004, ADR-0006, ADR-0007, PLAN-0003, PLAN-0004]
---

# Dashboard configuration controls against runtime

This is a code-path audit of the dashboard, API, resolved configuration snapshot,
native runtime and evidence models as of 2026-09-29. “Applied” means the current
runtime reads the setting and configures or enforces it. It does not imply live
provider or hardware validation. Draft values are persisted through the versioned
configuration APIs; published versions are immutable; a run records its resolved
snapshot and hash.

## Agent editor

| Dashboard control | Stored/API path | Runtime path and status |
|---|---|---|
| System prompt, verbatim greeting, node prompts, role prompts, prompt composition | `AgentConfig` / published version; resolved into `Run.resolved_config` | **Applied.** `NativePipelineHost` builds the model context and flow nodes from the resolved snapshot. A configured greeting is rendered and spoken as the opening; prompt composition and node context strategy are runtime inputs. |
| Contact variables and temporal variables | `contact_variables`, contact snapshot | **Applied with allow-listing.** Runtime exposes only selected contact values and derives local-time context from the contact timezone. Missing timezone remains unknown. |
| Flow nodes, initial node, transitions, terminal nodes, immediate response, append/reset context | `flow` JSON | **Applied for supported flow execution.** Flow is validated and managed by the host. Entry/exit actions support the zero-required-input registered `end_call` handler; other actions and background hooks are rejected at publication/runtime validation. Unsupported configured behavior cannot silently run. |
| Tool bindings, node tool selection, schemas and handler bindings | Versioned agent/tool records and exact resolved tool bindings | **Partially applied.** Registered handlers accepted by the live registry are executed and recorded. HTTP tools, background hooks and entry/exit actions are rejected by `prepare`; other unsupported handlers return errors. A saved binding alone is not proof of an executable integration. |
| LLM provider, model, temperature, maximum output tokens, top-p, reasoning | `llm` config | **Applied for Groq and Gemini.** Values configure their Pipecat services. Reasoning is provider constrained (Groq disabled, Gemini provider default); credentials remain server environment settings. |
| STT provider/model | `stt` config | **Applied for Sarvam `saaras:v3`.** Contract currently permits only that provider/model. Provider errors and available metrics are represented in operation evidence. |
| TTS provider, model, voice, language | `tts` config | **Applied for Sarvam and Cartesia** through the speech service builder, subject to provider capabilities and credentials. Model choices are fixed by the contract. Voice catalogs may be empty, in which case the editor preserves/accepts a provider voice ID. |
| Sarvam pace | `tts.pace` | **Applied for Sarvam.** Cartesia pace is not supported; the editor instead exposes Cartesia generation speed. |
| Cartesia generation volume, speed, emotion, pronunciation dictionary | `tts.cartesia` | **Applied when supplied** to Cartesia's Pipecat service. API/provider acceptance still depends on the selected voice and account. |
| Audio sample rate | `audio.sample_rate` | **Applied, editor read only.** The schema permits 8 or 16 kHz. Host, USB transport, modem format verification, capture and pipeline metrics use the resolved rate. |
| Audio channels, encoding, frame duration | `audio.channels`, `encoding`, `frame_ms` | **Fixed by schema** to mono, signed 16-bit little endian PCM and 20 ms frames. Displayed values are not editable controls. |
| VAD confidence, speech start/stop seconds, minimum volume | `vad` config | **Applied.** Values construct `SileroVADAnalyzer` for the call's sample rate. |
| Maximum call duration | `call_limits.max_duration_secs` | **Applied.** The execution runner wraps call work in this timeout. |
| Idle timeout | `call_limits.idle_timeout_secs` | **Applied.** Configures Pipecat's user turn idle timeout; host reprompts once, then ends after another idle period. |
| Interruptions / barge in | `call_limits.interruptions_enabled` | **Applied.** Selects the runtime turn strategy. Real carrier behavior still needs hardware validation. |
| Summarizer enabled, model/provider, temperature, max tokens, top-p, prompt | `context.summarizer` | **Applied when enabled.** Native Pipecat context summarization receives these values. The host builds the selected provider service using server credentials. |
| Summarizer context window, cadence, output budget, recent-message preservation | `context.summarizer` | **Applied with Pipecat semantics.** Context window, exchange-to-message cadence, summary budget and recent-message retention are passed to Pipecat's auto summarizer. Tool messages may cause earlier compaction. |
| Classifier enabled, entry/exit nodes, every-N exchanges, engine, prompts/model or Jev questions | `classifier` config | **Applied by native host** through LLM or Jev classification paths and persisted classifier evidence. Requires the relevant server-side key. Classifier cadence/model calls have no separate cost accounting yet. |
| Knowledge base selection and retrieval top-k, weights, RRF, result budget, timeout, wait mode/acknowledgement | `knowledge_base_ids`, `retrieval` in resolved agent config | **Applied by the live knowledge handler** using the shared retrieval service. Run evidence stores returned retrieval details. Minimum vector/keyword thresholds and reranking are shown read only; reranking is contract-limited to disabled. |
| Callback scheduling enabled, slot duration, minimum notice, roles and bookable people/calendar links | `callback_scheduling` in the agent version | **Applied by the human calendar scheduling path** where connected Google Calendar integrations are configured. This schedules appointments; it is distinct from automated telephone callback launch. |
| Per-agent pipeline log policy | `pipeline_logs` with inherit/enabled/disabled | **Applied at resolution and capture.** Effective value is snapshotted; the runtime writes a pipeline log only when enabled. Artifact ingestion enforces effective policy and workspace retention. |
| Agent name and draft note | Agent identity / version metadata | **Name is read only in this editor** because no rename operation is exposed there. Draft note is version metadata, not a runtime setting. |

## Workspace, call launch and operational controls

| Dashboard control | Stored/API path | Runtime path and status |
|---|---|---|
| Recording retention days | Workspace settings; effective value copied into resolved snapshot | **Persisted and enforced by artifact policy/expiry path** for registered artifacts. Runtime registration of every generated recording remains an operational dependency; retention cannot expire an unregistered file. |
| Pipeline log retention days | Workspace settings; effective value copied into resolved snapshot | **Persisted and enforced for registered pipeline-log artifacts.** It does not enable logging by itself. |
| Pipeline logs enabled by default | Workspace setting inherited by agent versions | **Applied during snapshot resolution.** An agent or call-level override can change the effective policy. |
| Automatic callbacks enabled | Workspace settings | **Gate is applied by `POST /callbacks/{id}/launch` in automatic mode.** There is no periodic due-callback scheduler in this worktree; the control does not itself cause a callback to launch. Manual launch remains available. |
| Callback due window | Workspace settings | **Applied by the automatic launch endpoint** together with the one-attempt limit. A missed window requires manual launch. |
| Per-call logging override in Quick Dial | Call request, then resolved snapshot | **Applied to this run's effective logging setting.** It does not alter workspace or agent defaults. |
| Telephony provider, endpoint, connected number, destination | Call request and endpoint/integration records | **Dispatch is wired for current SIM7600 and Twilio paths.** SIM7600 requires a claimed configured endpoint; Twilio requires a connected voice-capable number. Provider credentials remain backend-only. This selection does not make every agent action handler available. |
| Endpoint identity, serial/audio ports, baud rate and timeout | Runtime endpoint record | **Used by endpoint claim/driver and SIM7600 transport.** Endpoint diagnostics report observed availability; saved endpoint details do not prove hardware readiness. |
| Run transcript and operation timeline | Run evidence endpoints and `TraceSpan` rows | **Persisted for observed operations.** Native observer records LLM/STT/TTS, speech, playback, timings and supported Pipecat metrics; spool delivery can report incomplete evidence. This is operational evidence, not pricing persistence. |
| Run-detail LLM token summary | Sum of persisted LLM span token fields | **Displayed when present, marked partial/not recorded when coverage is incomplete.** Some total-token values are derived from prompt plus completion counts. It does not cover STT/TTS usage, price, currency or a guaranteed billable quantity. |

## Gaps and interpretation

- API validation, database persistence, publication and snapshot resolution confirm that
  a setting was accepted and pinned. They do not establish that a particular provider
  account accepts it or that modem/carrier behavior matches expectations.
- Unsupported runtime features fail explicitly at preparation or handler execution.
  In particular, HTTP tools, background hooks, and non-zero-input node actions are
  not made executable by appearing in the editor.
- Some configuration fields are intentionally fixed/read only, and some diagnostics
  are incomplete. The UI should preserve explicit “not supported”, “not recorded” and
  “partial” states rather than imply a working effect.
- Current trace spans hold provider/model and nullable usage/latency fields. The
  accounting module at `packages/voice_runtime/voice_runtime/execution/accounting.py`
  calculates provider-neutral estimated costs in memory, but no durable usage attempt,
  pricing catalog, cost API or cost UI is wired. See
  [PLAN-deferred-usage-pricing.md](plan/PLAN-deferred-usage-pricing.md).

## Code landmarks

- Dashboard editor: `apps/dashboard/src/pages/agents/` and
  `apps/dashboard/src/pages/settings/index.tsx`.
- Snapshot resolution: `apps/api/voice_api/services/resolution_service.py`.
- Contracts/capabilities: `packages/voice_runtime/voice_runtime/contracts/`.
- Host and observation: `packages/voice_runtime/voice_runtime/execution/native.py`,
  `speech.py`, and `observer.py`.
- Persisted evidence: `apps/api/voice_api/models/evidence.py` and
  `apps/api/voice_api/services/evidence_service.py`.
- Run token display: `apps/dashboard/src/pages/runs/detail.tsx`.
