# ISSUE-012 Legacy per-frame speech recognition did not produce final transcripts

Status: Implemented adapter change; provider acceptance is separate. Reviewed October 15, 2026.

## Observed problem

Audio could be captured while the older per-frame WAV speech path did not emit final transcription. Recorded audio alone did not prove successful STT delivery or endpointing.

## Implemented behavior

The configurable runtime constructs SarvamRealtimeSTTService with raw PCM and configured endpointing. The registry exposes current supported identifiers; legacy saved models remain readable but require upgrade for execution.

## Source

- [packages/voice_runtime/voice_runtime/execution/speech.py](../../packages/voice_runtime/voice_runtime/execution/speech.py)
- [packages/voice_runtime/voice_runtime/execution/native_helpers.py](../../packages/voice_runtime/voice_runtime/execution/native_helpers.py)

## Regression coverage

- [test_speech_service_construction.py](../../tests/unit/test_speech_service_construction.py) — `test_sarvam_settings_and_credentials_reach_service_constructors`.
- [test_speech_service_construction.py](../../tests/unit/test_speech_service_construction.py) — `test_saaras_uses_realtime_server_vad_and_codemix`.
- [test_speech_service_construction.py](../../tests/unit/test_speech_service_construction.py) — `test_realtime_server_vad_does_not_construct_local_smart_turn`.
- [test_speech_service_construction.py](../../tests/unit/test_speech_service_construction.py) — `test_cartesia_settings_credentials_and_audio_format_reach_constructor`.
- [test_speech_service_construction.py](../../tests/unit/test_speech_service_construction.py) — `test_unsupported_provider_raises_without_constructing_wrong_service`.
- [test_speech_service_construction.py](../../tests/unit/test_speech_service_construction.py) — `test_legacy_sarvam_model_is_rejected`.

## Verification limits

Provider-side model availability can change. Retain the original replay evidence locally; fake service construction is not a fresh live transcription test.

These links identify existing coverage. See [verification record](verification.md) for commands rerun during this review. Follow the [regression guide](../testing/regression-tests.md) before changing behavior.
