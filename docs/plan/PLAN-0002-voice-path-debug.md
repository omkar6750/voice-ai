# Voice path debugging

Scope: native serial PCM transport, startup order, AT response timing, plain
pipeline logs, and input/output/mixed WAV recordings. No DB or dashboard changes.

Ranked hypotheses and checks:
1. Startup stops before pipeline execution. Validate Flows and pipeline setup
   without dialing, then dial only after pipeline reports ready.
2. AT read timeout is confused with command timeout. Test delayed and fragmented
   responses against a bounded command deadline. Never assume timeout means success.
3. USB PCM endpoint opens too late. Open both ports before PCM registration and
   dial, then verify registration explicitly.
4. Output is sent faster than realtime. Measure 320-byte writes at 20 ms intervals.

Evidence from previous attempts: first stopped in Flows initialization; later
attempts stopped at CPCMREG activation. Providers were constructed but pipeline
execution never began. No previous audio recordings exist to recover.

Keep configuration in scripts/demo_call.py. Store private logs and three WAVs
under ignored data/recordings/<call-id>/. Record actual serial RX/TX on a shared
timeline, not all generated TTS (which may be discarded during interruption).
