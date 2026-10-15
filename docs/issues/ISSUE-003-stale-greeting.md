# ISSUE-003 Interrupted held speech could resume after voicemail detection

Status: Implemented for the gate race. Reviewed October 15, 2026.

## Observed problem

The voicemail TTS gate held frames outside normal processor queues. Interruption could clear ordinary queues while an old greeting remained held or was being released.

## Implemented behavior

Invalidate held audio/text/boundary frames on interruption and shutdown, fence release by epoch and reject late canceled TTS context IDs. Fresh responses retain their order.

## Source

- [packages/voice_runtime/voice_runtime/execution/voicemail.py](../../packages/voice_runtime/voice_runtime/execution/voicemail.py)

## Regression coverage

- [test_voicemail_tts_gate.py](../../tests/unit/test_voicemail_tts_gate.py) — `test_interruption_before_verdict_discards_old_audio_and_text`.
- [test_voicemail_tts_gate.py](../../tests/unit/test_voicemail_tts_gate.py) — `test_interruption_during_release_stops_remaining_old_frames`.
- [test_voicemail_tts_gate.py](../../tests/unit/test_voicemail_tts_gate.py) — `test_new_response_arriving_during_interrupted_release_is_preserved`.
- [test_voicemail_tts_gate.py](../../tests/unit/test_voicemail_tts_gate.py) — `test_shutdown_cannot_release_held_speech`.

## Verification limits

Late context-free provider frames still rely on provider cancellation. This fix does not provide exact spoken-word alignment.

These links identify existing coverage. See [verification record](verification.md) for commands rerun during this review. Follow the [regression guide](../testing/regression-tests.md) before changing behavior.
