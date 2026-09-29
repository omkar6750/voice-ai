# Handoff 003: provider and Pipecat runtime capability audit

## Objective

Audit which saved provider/runtime settings are truly effective in the live
Pipecat host, which are unsupported, and which need provider-specific adapters.
Produce an implementation-ready correction plan without changing language
switching or adding Krisp.

## Current implementation

Primary runtime:

- `packages/voice_runtime/voice_runtime/execution/native.py`
  - `build_speech_services()`
  - `build_user_aggregator_params()`
  - `NativePipelineHost.prepare()`
- `packages/voice_runtime/voice_runtime/contracts/providers.py`
- `packages/voice_runtime/voice_runtime/contracts/agent.py`
- `apps/api/voice_api/services/resolution_service.py`
- `apps/api/voice_api/services/provider_registry.py`
- `apps/dashboard/src/pages/agents/ModelsPanel.tsx`
- `apps/dashboard/src/pages/agents/AudioPanel.tsx`
- `apps/dashboard/src/pages/agents/ContextPanel.tsx`

The host currently constructs Sarvam, Cartesia, Groq, and Gemini services
directly. It applies VAD, call limits, static TTS language, Cartesia generation
settings, and optional context summarization. It rejects HTTP tools and generic
node actions during preparation.

Important contract fields to classify:

```text
audio.sample_rate / frame_ms
vad.confidence / start_secs / stop_secs / min_volume
call_limits.max_duration_secs / idle_timeout_secs / interruptions_enabled
llm provider/model/temperature/max_tokens/top_p/reasoning_effort
stt provider/model
tts provider/model/voice/language/pace/cartesia
context.summarizer.*
flow.prompt_composition
pipeline_logs
language.default_language / supported_languages
background_hooks / entry_actions / exit_actions
```

## Web-research instructions

The research agent has no repository, installed package, or CLI access. Search
official Pipecat documentation and public source for `LLMUserAggregatorParams`,
`LLMAssistantAggregatorParams`, `CartesiaTTSService`, `SarvamSTTService`,
context summarization, `LLMContextAggregatorPair`, VAD configuration, and
provider metrics. Search official provider documentation for Groq, Gemini,
Sarvam, Cartesia, and any relevant model-specific limitations.

Compare versioned Pipecat documentation or release notes around 1.11 with the
current docs. Check constructor signatures, event names, frame behavior,
provider metrics, and summarizer concurrency. Do not claim that a setting is
effective merely because a provider SDK accepts a similarly named parameter.

## Required deliverable

Create a table for every setting:

```text
serialized → validated → resolved → consumed by runtime → evidenced → shown in UI → tested
```

Classify each as effective, unsupported, pending, dead, or misleading. Include
the exact file/line area, the smallest implementation change, and tests needed.
Separate provider capability metadata from provider credentials. Do not design
automatic language switching or Krisp integration in this handoff.
Attach source links to each effective/unsupported conclusion and explicitly
mark conclusions that require a runtime smoke test because web documentation
cannot prove them.
