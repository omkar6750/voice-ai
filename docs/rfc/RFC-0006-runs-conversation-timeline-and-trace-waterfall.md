---
id: RFC-0006
title: Runs, conversation timeline, and turn waterfall trace inspection surface
status: Proposed
version: 1
date: 2026-09-23
authored_by: omkar
related: [RFC-0001, RFC-0002, RFC-0003, RFC-0004]
---

# RFC-0006 · Runs, conversation timeline, and turn waterfall trace inspection surface

## Implementation amendment, 2026-09-24

- Run owns timeline; Call exists for telephony. Exchanges group greeting or caller input with later provider requests/tools/playback; messages remain speaker turns. Show overlapping spans and interruption, with background result origin and consumption links.
- Provider TTFT is request-to-first-token. User-perceived response latency is end-of-speech-to-first-playback. TTS first audio and playback start differ. Missing metrics stay unknown.
- Initial recordings are full caller, agent and mixed WAV tracks. Per-turn WAV deferred. Seeking needs recording origin and explicit offsets.
- Current call path does not prove final messages/spans reach timeline. Show evidence completeness. Register artifacts with relative paths, typed track kinds and measured metadata. Authenticated audio fetch must not put Bearer token in URL.
- Raw pipeline logs are optional expiring files; default view shows finalized evidence. Poll until explicit terminal status and evidence flush.

## 1. Context

The Voice AI platform executes multi-turn conversations over cellular hardware (SIM7600 USB modem) and browser WebSocket transports. A voice call is a cascaded, real-time pipeline involving Silero VAD, Sarvam streaming STT, Groq/Qwen LLM inference, function calling, and Sarvam/Cartesia neural TTS streaming back over serial PCM.

Understanding why a call succeeded or failed, where latency was introduced, what the agent "thought", and how the customer reacted requires a purpose-built observability surface. Traditional APM span lists fail because voice AI operations are fundamentally organized around **conversation turns and spoken exchanges**.

## 2. Goals

- Provide a split-pane master-detail view of all historical and active voice runs.
- Design a turn-grouped **Waterfall Trace Visualization** answering *"Why did this turn take this long?"* with clear breakdowns of VAD endpointing, STT finalization, LLM TTFT, tool execution, TTS synthesis, and audio playback.
- Design a clean, human-readable **Conversation Transcript** with progressive disclosure for turn diagnostics, interruptions, and tool actions.
- Provide synchronized selection between transcript turns, waterfall span groups, and audio playback.
- Deliver transcript, operation timing, analysis and recording views. Initial audio artifacts are three full-call WAV tracks. Raw spool events are internal ingestion detail, not default UI.

## 3. Non-Goals

- Generic server APM infrastructure unrelated to voice pipeline turns.
- In-memory transcript editing or retrospective modification of immutable call evidence.

## 4. Routes

- `/runs` — Master runs table with search, status filters, duration, and agent selectors.
- `/runs/:runId` — Master-detail split view:
  - Left pane (`w-80`): Fast run switcher with outcome dots and search.
  - Center/Right main canvas: Run header, KPI summary row, and inspection lenses:
    - `?lens=waterfall` — Turn waterfall timing and latency breakdown.
    - `?lens=transcript` — Conversational dialogue turns and tool results.
    - `?lens=split` — Side-by-side synchronized transcript + turn trace.
    - `?lens=summary` — Post-call analysis, classifications, and facts.
    - `?lens=raw` — Raw OTel spans, payloads, spooled events, and pipeline logs.

## 5. API Dependencies

### Consumed Existing APIs
- `GET /api/v1/runs` — List all runs with channel, status, limits, and timestamps.
- `GET /api/v1/runs/{run_id}` — Run metadata, resolved config snapshot, contact snapshot, and call ID.
- `GET /api/v1/runs/{run_id}/timeline` — Complete structured execution timeline:
  - `exchanges[]` — Ordered dialogue exchanges.
  - `messages[]` — Finalized user and assistant messages (`interrupted: boolean`).
  - `spans[]` — Trace spans with OTel IDs, durations, TTFB, TTFA, tokens, and payloads.
  - `tools[]` — Tool invocations with arguments and results.
  - `flow_visits[]` — State machine node entries and exits.
  - `tool_results[]` — Ordered intermediate and final tool outputs.
- `GET /api/v1/runs/{run_id}/analysis` — Derived evidence (classifications, summaries, contact facts).
- `GET /api/v1/runs/{run_id}/artifacts` — Registered WAV recordings and pipeline log files.
- `GET /api/v1/artifacts/{artifact_id}/file` — Direct audio streaming / log download.
- `POST /api/v1/runs/{run_id}/reconcile` — Recover uncertain runs with dead worker locks.

## 6. Layout & Visual Structure

### 6.1 Run Detail Header & KPI Row
```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ RUNS / 43638018   Deepankar Paria (+91 73875 01703)   [🟢 Completed]  [Agent: Maya v1] │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ Duration: 4m 12s │ Turns: 8 │ TTFT (avg): 240ms │ TTFA (avg): 580ms │ Cost: $0.0142    │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ [📊 Waterfall Trace]   [💬 Transcript]   [⚡ Split View]   [📋 Summary]   [🔍 Raw Events]│
└────────────────────────────────────────────────────────────────────────────────────────┘
```

### 6.2 Synchronized Split-Screen View (`?lens=split`)
```text
┌──────────────────────────────────────┬─────────────────────────────────────────────────┐
│ Conversational Transcript            │ Turn 3 Waterfall Breakdown                      │
├──────────────────────────────────────┼─────────────────────────────────────────────────┤
│ [Turn 1 · Caller] "Hello?"           │ Total Turn Duration: 740 ms                     │
│ [Turn 1 · Maya] "Good evening..."    │                                                 │
│                                      │ VAD Endpointing   [━━━━]                120 ms  │
│ [Turn 2 · Caller] "Yes, I am moving  │ Sarvam STT        [━━━━━━]              180 ms  │
│  to Indian Maximalism jewellery..."  │ Groq LLM (TTFT)        [━━]              95 ms  │
│                                      │ LLM Generation         [━━━━━━━]        220 ms  │
│ ► [Turn 3 · Caller] "What timeline   │ Tool: change_node           [━━]         30 ms  │
│   can you deliver the UI?"           │ Sarvam TTS (TTFA)              [━━━━━]  190 ms  │
│                                      │ Audio Playback                 [━━━━━━━━] 3.2s  │
│ [Turn 3 · Maya] "We can complete the │                                                 │
│  entire UI in 2 to 3 days once..."   │ ┌─────────────────────────────────────────────┐ │
│                                      │ │ TTFT: 95ms • TTFA: 495ms • Audio: 3.2s      │ │
│ [Turn 4 · Maya] [Tool: WhatsApp]     │ │ Tokens: 142 in / 38 out (qwen3.8-27b)       │ │
│  "I just sent our catalog to your..."│ └─────────────────────────────────────────────┘ │
└──────────────────────────────────────┴─────────────────────────────────────────────────┘
```

## 7. Waterfall Visualization Architecture

### 7.1 Turn Grouping Logic
Raw pipeline spans are aggregated into **Turn Groups** keyed by exchange sequence:
1. **User Input Phase**:
   - Audio capture & VAD speech boundary detection (`started_at` to speech end).
   - STT streaming partials leading to finalized `ConversationMessage` (`role: 'user'`).
2. **Inference & Decision Phase**:
   - LLM Context Assembly span.
   - LLM Request span (metrics: `ttfb_ms` / `first_token_ms`, `prompt_tokens`, `completion_tokens`).
   - Function Calling / Tool Invocation span (`change_node`, `send_whatsapp_template`, `classify_jev`).
3. **Synthesis & Delivery Phase**:
   - Secondary LLM synthesis / generation (if tools yielded context results).
   - TTS Service span (metrics: `ttfa_ms`, audio bytes, chunk count).
   - Audio output buffer streaming to modem PCM.

### 7.2 Latency Metrics Formulation
- **Time-to-First-Token (TTFT)**: Monotonic elapsed time from user speech endpointing to first LLM token arrival.
- **Time-to-First-Audio (TTFA)**: Monotonic elapsed time from user speech endpointing to first synthesized PCM audio buffer emitted to hardware.
- **Critical Path Highlighting**: Visual horizontal bar highlighting which component contributed the largest percentage of delay before speech playback.

## 8. Post-Call Summary & Derived Analysis Lens

The `Summary` lens visualizes evidence generated by post-call background workers or live classifiers:
- **Lead Classification Card**: Temperature (`hot` / `warm` / `cold`), confidence score, and rationale.
- **Extracted Contact Facts**: Pinned key-value pairs (e.g., `Brand: Neotribe`, `Target Deadline: Diwali`, `Stock Status: Acquired`).
- **Context Summaries**: Bulleted recap of the conversation agreements and objections.
- **Action Item Tracker**: WhatsApp follow-up template delivery status and scheduled callbacks.

## 9. Raw Debug Drawer & Pipeline Artifacts

For advanced debugging, clicking any event or opening `?lens=raw` reveals:
- **Exact LLM Context**: Sanitized system instruction, prior turn memory, and tool pairs actually passed to inference.
- **OTel Trace & Span IDs**: Full 32-character trace ID and 16-character span IDs for cross-referencing external collectors.
- **Audio Waveform Player**: Embedded player streaming `input.wav` (caller audio), `output.wav` (agent voice), or `mixed.wav`.
- **Pipeline Log Viewer**: Monospace, line-numbered, searchable log viewer reading `pipeline.log` directly via the `/artifacts/{id}/file` endpoint.

## 10. Live Run Streaming & Polling

- When inspecting a run with `status = "running"`, the view initiates a 1500ms polling cycle on `GET /api/v1/runs/{id}/timeline`.
- New exchanges, live transcript turns, and ongoing spans animate into the timeline in real time.
- As soon as the call hangs up or the run reaches terminal status (`completed`, `failed`), polling ceases automatically.

## 11. Open Questions & Iteration Notes

1. *Audio Scrubbing Synchronization*: Can we synchronize the audio player's playback position (`currentTime`) with an active highlighting cursor in the transcript and waterfall timeline? (Design plans for an audio-turn time index map).
