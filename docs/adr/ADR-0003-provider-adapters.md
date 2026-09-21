---
id: ADR-0003
title: Keep provider imports behind adapters
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

The initial provider set is OpenAI STT, LLM, and TTS. Pipecat service imports live in `voice_runtime.providers`. Pipeline code consumes the returned processors. SIM7600 serial code lives in `voice_runtime.telephony`.

# Cost

The first provider choice is pragmatic, not permanent. Replacing it requires another adapter and configuration decision, not a pipeline rewrite.
