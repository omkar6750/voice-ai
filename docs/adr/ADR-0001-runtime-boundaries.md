---
id: ADR-0001
title: Keep API runtime and modem as explicit local boundaries
status: Accepted
version: 1
date: 2026-09-21
authored_by: codex
session: voice-ai-foundation-01
supersedes: null
superseded_by: null
related: [RFC-0001]
---

# Decision

FastAPI owns control-plane HTTP and persistence. Pipecat owns realtime audio and model execution. The SIM7600 adapter owns AT commands and call state. The runtime remains native on Windows.

# Cost

The first call lifecycle crosses a process boundary later than this slice. USB audio remains a measured hardware integration task, not a fake network transport.
