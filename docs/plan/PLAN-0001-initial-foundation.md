---
id: PLAN-0001
title: Initial working-agent foundation
status: Executed
version: 1
date: 2026-09-21
authored_by: codex
session: voice-ai-foundation-01
related: [RFC-0001, ADR-0001, ADR-0002, ADR-0003]
---

# RFC extraction

Minimum first working agent:

1. Windows-native runtime with Pipecat pipeline.
2. SIM7600 AT call control and USB audio selection.
3. One STT, LLM, and TTS provider set.
4. Agent prompt and tool names loaded from typed config.
5. FastAPI health/control boundary.
6. PostgreSQL schema for agent versions, contacts, and calls.

Required external services: OpenAI API, PostgreSQL, cellular network, and the SIM7600 modem. Ngrok, WhatsApp Cloud API, Clerk, and a public dashboard are not needed to validate the first local voice path.

Required files: `.env`, `pyproject.toml`, `docker-compose.yml`, Alembic config, runtime entrypoint, provider adapter, modem adapter, and tests.

Runtime boundary:

```text
FastAPI -> start command -> native voice runtime
voice runtime -> OpenAI services
voice runtime -> SIM7600 AT COM + Windows USB audio devices
FastAPI -> PostgreSQL
```

Provider boundary: business code uses local protocols or Pipecat processor contracts. Provider SDK imports stay in provider modules.

Initial tools: `classify_lead`, `send_whatsapp`, `schedule_callback` are names in typed config only. No external side effects are wired yet.

Deferred features: dashboard workflows, auth, WhatsApp, recordings, trace persistence, complete Pipecat Flows editing, RAG, analytics, and Raspberry Pi deployment.

Open questions and assumptions:

- The assignment file is empty, so RFC-0001 is authoritative.
- OpenAI is the first provider because one API key covers the initial STT, LLM, and TTS seam.
- SIM7600 USB audio should appear as Windows capture and playback devices, but exact device indexes and sample rate require hardware measurement.
- FastAPI to runtime command transport is deferred until the local runtime can place and sustain one call.

Risks:

- SIM7600 audio drivers may expose incompatible sample rates or full-duplex behavior.
- OpenAI TTS emits 24 kHz audio while cellular paths often use 8 kHz audio. Resampling must be tested with the real device.
- AT command timing and unsolicited modem notifications can race with command responses.

Exit evidence for this foundation: dependencies resolve, API health test passes, models import, migration renders, modem adapter unit tests pass, and dashboard production build succeeds.
