# Local voice-path test

Run from the development worktree. Agent, model, VAD and audio knobs live at the
top of `scripts/demo_call.py`. Read an existing env file explicitly; do not copy
a template over keys.

```powershell
uv run python scripts/demo_call.py --check --env-file C:\dev\GitHub\voice-ai\.env
uv run python scripts/demo_call.py --probe-providers --env-file C:\dev\GitHub\voice-ai\.env
uv run python scripts/demo_call.py --number <phone-number> --env-file C:\dev\GitHub\voice-ai\.env
```

`--check` validates services/Flows without provider requests or hardware.
`--probe-providers` exercises the real LLM/TTS pipeline without opening COM ports
or dialing. Its WAVs contain silence because no serial PCM was exchanged.
The normal command makes a real call, bounded to 120 seconds. Remote hangup or a
pipeline error cancels the pipeline and closes the call.

Each run creates `data/recordings/<UTC-time-and-id>/`:

- `pipeline.log`: startup, AT TX/RX, flow transitions, transcripts, LLM/TTS frames,
  VAD/interruption frames, sampled PCM counters and RMS, errors and cleanup.
- `input.wav`: caller PCM actually received from COM17.
- `output.wav`: PCM successfully written to COM17, after output pacing.
- `mixed.wav`: aligned, clipped sum. All WAVs use 8 kHz mono 16-bit PCM.

Gaps are silence on a shared host timeline. Generated TTS canceled before serial
write does not appear in output.wav. A successful serial write proves host
delivery, not remote acoustic playback. Logs and transcripts are private local
debug artifacts; keys are redacted and stack-local variable dumps are disabled.

Prior silent calls failed before PipelineWorker.run: Flows tool initialization
or AT activation aborted startup. Provider constructors in console logs were
not provider requests. Those calls did not capture audio and cannot be recovered.
Subsequent instrumented tests exposed a removed Groq model (404), then a required
initial user message (400). Correcting these allowed real speech generation.

The native path is COM17 -> Pipecat -> Sarvam -> Groq -> Cartesia -> COM17.
Flows controls prompts/tools; it does not carry PCM. See ADR-0005 for startup
ordering and the provider decision. Hardware evidence is in the per-run logs.
