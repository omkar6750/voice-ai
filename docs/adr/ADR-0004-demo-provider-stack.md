---
id: ADR-0004
title: Demo provider stack
status: Accepted
supersedes: ADR-0003
---

# Decision

The first working demo agent uses:

- Sarvam `saaras:v3` for speech-to-text;
- Groq `llama-3.1-8b-instant` for the LLM, with `reasoning_effort="none"`;
- Cartesia PCM TTS at 8 kHz for cellular audio output.

Provider SDK imports remain inside `voice_runtime.providers.demo`. The runtime consumes Pipecat service objects returned by that adapter.

# Rationale

This stack matches the required Indian-language STT path, provides a low-latency non-reasoning LLM, and emits audio in the SIM7600 USB PCM format. The provider choices are demo defaults and can later be replaced by another adapter without changing telephony or pipeline boundaries.