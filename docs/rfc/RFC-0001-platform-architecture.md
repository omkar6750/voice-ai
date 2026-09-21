---
id: RFC-0001
title: Voice AI platform architecture
status: Proposed
version: 1
date: 2026-09-20
authored_by: omkar
supersedes: null
superseded_by: null
related: []
---

# RFC-0001 · Voice AI platform architecture

Parent RFC for the Voice AI POC. It defines the overall system shape, runtime boundaries, deployment model, persistence, and demo architecture.

Detailed decisions such as the SIM7600 transport, Pipecat flow schema, tracing model, and WhatsApp integration belong in their own ADRs or RFCs.

## 1. Context

The assignment requires a working outbound sales voice agent that can:

- place a real phone call;
- hold a multi-turn conversation;
- qualify the lead;
- classify intent;
- trigger actions such as WhatsApp messages and callbacks;
- expose enough diagnostics to understand what happened during a call.

Twilio or another telephony provider is not currently available.

For the POC, calls are made through a SIM7600 modem connected directly to a Windows development machine over USB.

The system also needs a dashboard for:

- configuring agents and Pipecat flows;
- managing contacts;
- manually starting calls;
- viewing call history;
- inspecting transcripts and traces;
- demonstrating the system remotely.

The POC should stay simple while keeping clear seams that allow the SIM7600 to later be replaced by Twilio, SIP, or another telephony provider.

## 2. Architecture

The system is a modular monolith with a separate voice runtime boundary.

```text
                         INTERNET
                             │
                         ngrok HTTPS
                             │
               ┌─────────────▼─────────────┐
               │          FastAPI          │
               │                           │
 Browser ─────►│ REST / WebSocket API      │
               │ React dashboard           │
 Meta WA ─────►│ WhatsApp webhooks         │
               │ contacts / agents / calls │
               └─────────────┬─────────────┘
                             │ localhost
                    ┌────────▼────────┐
                    │  Voice Runtime  │
                    │                 │
                    │ Pipecat         │
                    │ Pipecat Flows   │
                    │ STT → LLM → TTS │
                    │ Actions         │
                    └─────┬──────┬────┘
                          │      │
               USB/COM    │      │ HTTPS
                          │      │
                  ┌───────▼───┐  └──────► WhatsApp Cloud API
                  │ SIM7600   │
                  │           │
                  │ AT COM    │
                  │ USB audio │
                  └─────┬─────┘
                        │
                   Cellular call


               ┌────────────────────┐
               │ PostgreSQL         │
               │ Docker             │
               │                    │
               │ agents / versions  │
               │ contacts / calls   │
               │ turns / traces     │
               │ actions / callbacks│
               └────────────────────┘
```

## 3. Process topology

Three main runtime components exist.

### FastAPI control plane

FastAPI owns normal application concerns:

- agents and configuration;
- contacts;
- call history;
- dashboard APIs;
- WhatsApp webhooks;
- trace queries;
- commands to start or stop calls.

FastAPI does not directly manage USB audio or modem hardware.

### Voice runtime

The realtime voice runtime runs natively on Windows.

It owns:

- Pipecat pipelines;
- Pipecat Flows;
- STT, LLM, and TTS;
- call lifecycle;
- realtime actions;
- SIM7600 interaction;
- runtime trace emission.

The API and runtime may live in the same repository but remain separate logical modules/processes.

### PostgreSQL

PostgreSQL is the shared persistent data store.

It runs in Docker because it has no realtime hardware requirements and benefits from reproducible local setup.

## 4. Hardware and Docker boundary

The SIM7600 and voice runtime will not run inside Docker for this POC.

The modem exposes hardware-specific interfaces including:

- serial COM ports for AT commands and call control;
- USB audio for caller audio and synthesized agent audio.

Keeping this native avoids unnecessary Windows → Docker VM → USB forwarding complexity.

Docker is initially used only for infrastructure such as PostgreSQL.

```text
Windows host
├── FastAPI
├── Pipecat runtime
├── SIM7600
├── ngrok
└── Docker
    └── PostgreSQL
```

## 5. Dashboard deployment

During development:

```text
React/Vite     :5173
FastAPI        :8000
Voice runtime  native Windows process
PostgreSQL     :5432 Docker
```

Vite runs independently to retain HMR.

For the final demo, React is built into a static distribution:

```bash
npm run build
```

FastAPI serves the resulting React files.

This produces one public application:

```text
Browser
   ↓
ngrok
   ↓
FastAPI :8000
   ├── /api/*
   ├── /webhooks/*
   └── React dashboard
```

Only FastAPI is exposed publicly.

The realtime SIM7600 audio path remains local and does not travel through ngrok.

## 6. Agent configuration

Agents are configured using Pipecat Flows.

The dashboard edits a data representation of the flow rather than generating Python code.

A versioned agent configuration contains approximately:

```text
Agent
└── AgentVersion
    ├── prompts
    ├── model/settings
    └── FlowConfig
        ├── initial node
        ├── nodes
        ├── transitions
        └── functions/actions
```

Typical nodes may include:

```text
introduction
    ↓
discovery
    ↓
qualification
    ↓
objection handling
    ↓
closing
```

Published versions should be immutable so an old call can always be associated with the exact configuration that produced it.

Draft configuration can continue changing independently.

## 7. Telephony boundary

Pipecat must not depend directly on SIM7600-specific implementation details.

Telephony is exposed through an internal transport abstraction.

Conceptually:

```text
TelephonyTransport
├── dial()
├── hangup()
├── read_audio()
├── write_audio()
└── call_state()
```

The first implementation is:

```text
SIM7600Transport
```

Future implementations may include:

```text
TwilioTransport
SIPTransport
```

Changing telephony providers should not require rewriting the agent or flow system.

## 8. Persistence

PostgreSQL stores structured application state.

The initial domain includes:

```text
agents
agent_versions

contacts

calls
call_turns
trace_events

actions
callbacks
```

Agent flow definitions and provider-specific metadata may use PostgreSQL `JSONB` where the structure is naturally dynamic.

Core relationships such as agents, contacts, calls, and actions remain relational.

## 9. Call recordings

Audio recordings are not stored directly in PostgreSQL.

For the POC they are stored locally:

```text
data/
└── recordings/
    └── <call-id>/
        ├── input.wav
        ├── output.wav
        └── mixed.wav
```

PostgreSQL stores recording metadata and paths.

This allows local storage to later be replaced with object storage without changing the call domain model.

## 10. Tracing

The runtime emits append-only trace events.

Examples include:

```text
call.started
call.answered
call.completed

turn.started
turn.completed

stt.started
stt.completed

llm.started
llm.first_token
llm.completed

tts.started
tts.first_audio
tts.completed

flow.node.entered

action.started
action.completed
```

The dashboard derives its timeline and per-turn diagnostics from these events.

Application tracing should not expose Pipecat internals directly as the dashboard data model.

## 11. Actions and WhatsApp

Actions invoked by the agent are implemented behind explicit application interfaces.

Initial actions include:

```text
send_whatsapp
schedule_callback
classify_lead
```

WhatsApp communication uses the WhatsApp Cloud API.

Incoming webhooks are received through:

```text
ngrok
   ↓
FastAPI
   ↓
/webhooks/whatsapp
```

Action attempts and results are persisted so they remain visible after the call finishes.

## 12. Remote demo

For the POC the complete system runs on the Windows laptop.

A reviewer accesses:

```text
https://<ngrok-domain>
```

and can start a call from the dashboard.

```text
Dashboard
   ↓
FastAPI
   ↓
Voice Runtime
   ↓
SIM7600
   ↓
Cellular Network
```

The laptop therefore acts as both the application server and telephony edge device for the demo.

## 13. Raspberry Pi and remote runtime

Moving the SIM7600 to a Raspberry Pi is intentionally deferred.

If required later, the existing voice-runtime boundary allows:

```text
Cloud / Laptop
Control Plane
      │
      │ start-call / events
      ▼
Raspberry Pi
Voice Runtime
      │
      ▼
SIM7600
```

The Raspberry Pi would execute Pipecat close to the modem rather than forwarding raw realtime audio to the control plane.

This is not required for the initial assignment.

## 14. Repository shape

```text
elevate-voice/
│
├── apps/
│   ├── api/
│   │   └── FastAPI
│   │
│   └── dashboard/
│       └── React + Vite
│
├── packages/
│   └── voice_runtime/
│       ├── pipeline/
│       ├── flows/
│       ├── telephony/
│       │   ├── base.py
│       │   └── sim7600.py
│       ├── actions/
│       └── tracing/
│
├── data/
│   └── recordings/
│
├── migrations/
├── docker-compose.yml
└── pyproject.toml
```

Exact package boundaries may change as implementation begins. The architectural separation between control plane, voice runtime, telephony adapter, and persistence should remain.

## 15. Decisions established by this RFC

The initial architecture therefore follows these constraints:

1. Build a modular monolith rather than independent microservices.
2. Keep the realtime Pipecat/SIM7600 runtime native on Windows.
3. Use Docker for PostgreSQL, not for modem/audio handling.
4. Keep FastAPI and the React dashboard in one repository.
5. Serve the React production build through FastAPI for the demo.
6. Expose only FastAPI through ngrok.
7. Use Pipecat Flows as versioned, data-driven agent configuration.
8. Hide SIM7600 behind a telephony transport abstraction.
9. Store structured operational data in PostgreSQL.
10. Store recordings as files and keep their metadata in PostgreSQL.
11. Model tracing as application-owned append-only events.
12. Treat Raspberry Pi or cloud deployment as a later runtime placement change rather than part of the initial POC.

## 16. Follow-up decisions

This RFC intentionally does not define implementation details for:

- SIM7600 call and audio transport;
- Pipecat pipeline construction;
- Pipecat Flow schema and dashboard editor;
- database tables and migrations;
- runtime ↔ API communication;
- trace event schema;
- WhatsApp templates and webhook handling;
- STT, LLM, and TTS provider selection;
- language and code-switching strategy.

Those decisions should be recorded independently as implementation progresses.