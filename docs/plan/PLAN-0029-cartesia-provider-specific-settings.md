---
id: PLAN-0029
title: Cartesia provider-specific TTS settings
status: Proposed
date: 2026-09-27
related: [PLAN-0020, PLAN-0028]
---

# Cartesia provider-specific TTS settings

## Decision

Add typed, provider-specific persisted configuration for Cartesia `generation_config` (`volume`, `speed`, `emotion`) and `pronunciation_dict_id`; show these controls only when Cartesia is selected. Do not reuse Sarvam `pace` as Cartesia speed. Current native host passes only model/voice/language for Cartesia. Validate against the *installed Pipecat version and selected Cartesia model*, because allowed emotion/speed/volume ranges or dictionary compatibility may vary. Credentials remain environment-only and are never returned to the dashboard.

## Implementation sequence

1. Inspect installed `CartesiaTTSService.Settings` and `GenerationConfig` schemas with Context Hub/source; confirm supported `sonic-3` fields and documented ranges. Record whether unset means provider default and whether pronunciation dictionary IDs can be verified without a network call.
2. Extend `TTSConfig` with discriminated provider-specific options (`sarvam` pace versus `cartesia` nested generation/pronunciation). Keep backward-compatible read of existing published agent snapshots; avoid misleading default values that silently change synthesis. Update provider capability metadata and resolve/publish validation.
3. Pass validated Cartesia settings into native Pipecat service construction. Ensure retries/reconnections preserve the same settings and evidence records nonsecret effective values. Fail clearly on invalid combinations before dialing.
4. Add conditional dashboard controls with descriptions and validation, model/voice compatibility hints, null/default reset behavior, and a concise test-synthesis preview if a safe preview path exists. Generate API client types; do not hand-maintain duplicate DTOs.
5. Cover settings round trip from draft → published version → resolved snapshot → live service, and verify absence of Cartesia fields from Sarvam requests. Ensure old `pace` remains Sarvam-only and UI does not imply otherwise.

## Tests and acceptance

- Unit tests for valid/invalid volume/speed/emotion/dictionary ID, omitted defaults, old published config, provider switching, and native service arguments.
- API/dashboard round-trip and generated type/build checks; mocked provider compatibility failures are surfaced before call start.
- One provider-backed synthesis test (when key is available) confirms audible/effective generation settings without asserting subjective speech quality from unit tests.

Refs: [Pipecat Cartesia TTS API](https://docs.pipecat.ai/api-reference/server/services/tts/cartesia), [Pipecat service settings](https://docs.pipecat.ai/pipecat/fundamentals/service-settings).
