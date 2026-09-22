---
id: ADR-0005
title: Native PCM call test and available Groq model
status: Accepted
version: 1
date: 2026-09-21
authored_by: codex
session: fix-voice-transport
supersedes: ADR-0004
superseded_by: null
related: [RFC-0001, ADR-0001]
---

Keep Sarvam STT and Cartesia TTS. Use Groq `qwen/qwen3.8-27b` with
`reasoning_effort="none"`: the account's live model list contains it, a live
completion succeeded, and `llama-3.1-8b-instant` returned model_not_found.
This is a verified compatible choice, not a measured fastest-model claim.
Qwen needs an initial user message; use an explicitly synthetic start instruction.

The POC runs natively and needs no WebSocket/Docker audio hop. Open COM17 during
pipeline setup, dial on COM16 only after pipeline startup, await an active call,
then enable `AT+CPCMREG=1` and start the greeting. Hang up before `AT+CPCMREG=0`.
USB audio is 8 kHz, mono, signed 16-bit little-endian PCM, paced in 320-byte/20-ms
chunks. Serial read timeout is not a complete AT command deadline.

Capture plain pipeline and AT logs plus actual serial RX/TX WAVs on one host
timeline. The mixed recording sums and clips both streams. These are diagnostic
recordings, not proof of acoustic playout at the remote phone. Keep files local
under ignored `data/recordings/`; no new service, database, or trace framework.

Sources:
- https://files.waveshare.com/upload/a/af/SIM7500_SIM7600_Series_AT_Command_Manual_V3.00.pdf
- https://console.groq.com/docs/reasoning
- Installed Pipecat 1.11.0 source and live provider/modem logs.
