# ADR-0015 · Runtime-owned provider capabilities

Status: Accepted  
Date: 2026-09-27  
Related: [PLAN-0015](../plan/PLAN-0015-provider-model-configuration.md),
[ADR-0004](ADR-0004-provider-boundaries.md),
[ADR-0005](ADR-0005-runtime-configuration.md),
[ADR-0006](ADR-0006-versioned-configuration.md)

## Context

The agent Models panel had a mixed contract. LLM providers and live model lists came from `/providers`, but STT was read-only and TTS provider/model, language, and voice controls were partly hard-coded in the dashboard. The provider endpoint returned an untyped dictionary with no declaration of which fields the runtime actually supports.

The installed Pipecat version is 1.11.0. Context Hub and local introspection confirmed these relevant settings:

- Sarvam STT: model.
- Sarvam TTS: model, voice, language, and pace.
- Cartesia TTS: model, voice, and language. Pace is not a Cartesia setting.

## Decision

Provider capability metadata is owned by the runtime contract and exposed by a typed API catalog. The API may add credential/catalog state, but the dashboard never receives provider secrets.

The public response is:

```text
ProviderCatalogResponse
  └── ProviderEntryResponse
       ├── provider
       ├── slots
       ├── models / models_by_slot
       ├── languages / voices
       ├── fields[name].runtime_supported
       ├── status                 # credential/catalog state
       └── runtime_status         # supported/pending/unavailable
```

Static runtime capabilities are defined once in `voice_runtime.contracts.providers.RUNTIME_PROVIDER_CAPABILITIES`. Live Groq and Gemini model discovery remains cached and provider-backed, while the runtime-supported speech capabilities are deterministic.

Agent configuration remains strict. STT is currently limited to `sarvam/saaras:v3`. TTS validates the provider/model pair:

```text
sarvam   → bulbul:v3
cartesia → sonic-3
```

This validation runs anywhere `AgentConfig` is parsed, including create, draft-update, publish, resolution, and runtime snapshot use.

## Data flow

```text
runtime capability definition
        │
        ├── API ProviderCatalogResponse
        │       └── OpenAPI → generated TypeScript
        │                       └── Models panel
        │
        └── AgentConfig validation
                └── resolved snapshot
                        └── build_speech_services
                                └── Pipecat constructors
```

`build_speech_services` is the runtime boundary used by the native host. It passes selected values directly into Pipecat settings. It also fails closed on an unsupported provider rather than silently falling back.

## UI behavior

The Models panel renders STT/TTS providers and models from the catalog. Voices are rendered as a select when the provider exposes a voice catalog and as a provider voice-ID input otherwise. Languages are rendered as a select when enumerated and as a text input otherwise. A field whose capability says `runtime_supported=false` is read-only and explains why.

For the current catalog, Cartesia pace is therefore visible but not editable, and is never passed into the Cartesia constructor. Provider status is shown separately from runtime support so an unconfigured credential is not confused with an unsupported runtime.

## Verification

- Context Hub and local Pipecat 1.11.0 inspection confirmed constructor fields.
- Focused provider catalog and constructor tests: 4 passed.
- Full backend suite: 109 passed, 31 skipped.
- Ruff: passed.
- OpenAPI export: passed.
- Dashboard contract generation and production build: passed.

The existing repository has unrelated baseline warnings: Pipecat deprecation warnings, two test mock coroutine warnings, and the earlier documented Alembic schema drift. No migration was needed for this plan.

## Known limitations

- STT remains Sarvam-only until another runtime adapter is intentionally added.
- Sarvam and Cartesia voice catalogs are not fetched dynamically; voice IDs stay editable text when no catalog is available.
- Provider usage and credits were evaluated in Plan 0016 and removed because
  the configured providers do not expose supported account usage APIs.
