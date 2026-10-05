# PLAN-0015 · Provider and model configuration

Status: completed

## Existing facts

- STT is exposed through the provider capability catalog. Sarvam `saaras:v3` and `saaras:v4` are selectable; Gnani `gnani-prisma-v2.5` remains supported.
- TTS supports Sarvam `bulbul:v3` and Cartesia `sonic-3`. Pipecat 1.11.0 exposes model, voice, and language for Cartesia, while pace is not a Cartesia runtime setting.
- The old provider catalog was an untyped dictionary and the dashboard had static TTS provider/model choices, fallback models, hard-coded languages, and a free-form voice input.

## Scope

- Make STT/TTS/model configuration capability-driven.
- Expose only fields supported by the provider/runtime contract.
- Prove selected values reach runtime constructors.

Implementation completed in:

- `packages/voice_runtime/voice_runtime/contracts/providers.py`
- `apps/api/voice_api/schemas/providers.py`
- `apps/api/voice_api/services/provider_registry.py`
- `apps/api/voice_api/api/v1/endpoints/providers.py`
- `packages/voice_runtime/voice_runtime/execution/native.py`
- `apps/dashboard/src/pages/agents/ModelsPanel.tsx`
- `apps/dashboard/src/pages/agents/types.ts`

## Contracts

- `ProviderCatalogResponse` and its nested Pydantic models include slots, models, per-slot models, languages, voices, editable/runtime-supported fields, credential/catalog status, runtime support status, and check time.
- The catalog is returned by `/api/v1/providers` with a FastAPI response model and is exported through the normal OpenAPI/generated-TypeScript flow.
- Runtime-owned capability definitions are shared with the API catalog; the API adds credential status without exposing credentials.
- `TTSConfig` rejects provider/model mismatches (`sarvam` must use `bulbul:v3`, `cartesia` must use `sonic-3`). `STTConfig` validates Sarvam v3/v4 and Gnani model compatibility.

## Runtime and frontend behavior

- The Models tab reads all STT/TTS providers, models, languages, voices, and field support from `/providers`; it no longer contains hard-coded provider or model options.
- Providers expose credential/catalog state and runtime support separately.
- Cartesia pace is shown as read-only with an explicit unsupported explanation; no unsupported setting is silently sent to Pipecat.
- `build_speech_services` constructs the exact Sarvam STT (v3 or v4), Gnani STT, Sarvam TTS, or Cartesia TTS service from the resolved snapshot. Cartesia now receives the selected model, voice, and language.
- Resolved snapshots and evidence continue to identify the selected provider and model values.

## Tests and acceptance

- Focused provider catalog and constructor tests pass.
- The runtime constructor boundary test proves snapshot values reach the selected Pipecat service settings; existing agent publication/activation integration tests cover the surrounding version lifecycle.
- Invalid provider/model combinations are rejected by the shared Pydantic contract.
- Full suite: `109 passed, 31 skipped`.
- `uv run ruff check .` passes.
- `uv run python scripts/export_openapi.py`, dashboard `npm run generate`, and dashboard `npm run build` pass.

## Manual verification

- Open an editable agent draft and open Models.
- Confirm STT provider/model and TTS provider/model come from the provider catalog, with status labels and no provider credentials in the response.
- Switch TTS between Sarvam and Cartesia and verify the supported fields change; Cartesia pace is visibly unsupported.
- Save, publish, activate, and start a call.
- Inspect the resolved run snapshot and provider evidence to verify the selected STT/TTS providers and models. A live Cartesia call also verifies voice and language at the provider boundary.

## Non-goals

- No provider credentials in the dashboard.
- No provider credential-management UI or quota/credit reporting; that is Plan 0016.
- No new STT vendor was added; the current runtime still supports Sarvam only.
- No migration was required because the existing agent configuration JSON shape already stores the selected provider/model fields.
