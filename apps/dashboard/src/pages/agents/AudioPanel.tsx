import { ReadOnlyValue } from "@/components/record-page";
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import { NativeSelect } from "@/components/ui/native-select";
import { NumberField } from "./ConfigFields";
import type { AgentConfig } from "./types";

export function AudioPanel({
  config,
  change,
  disabled,
}: {
  config: AgentConfig;
  change: (next: AgentConfig) => void;
  disabled: boolean;
}) {
  const sarvamRealtime =
    config.stt.provider === "sarvam" && config.stt.model === "saaras:v4";

  return (
    <section className="grid max-w-5xl gap-8 lg:grid-cols-2">
      <div className="flex flex-col gap-4">
        <h2 className="text-base font-semibold">Audio and VAD</h2>
        <FieldGroup>
          <ReadOnlyValue
            label="Input/output sample rate"
            value={`${config.audio.sample_rate / 1000} kHz`}
            reason="Shown from saved config. Rate changes are not available in this editor."
          />
          {sarvamRealtime ? (
            <>
              <NumberField
                id="sarvam-vad-threshold"
                label="Sarvam VAD threshold"
                value={config.stt.realtime.threshold}
                min={0}
                max={1}
                step={0.05}
                hint="Higher values reject more background noise; start at 0.3."
                disabled={disabled}
                onChange={(threshold) =>
                  change({
                    ...config,
                    stt: {
                      ...config.stt,
                      realtime: { ...config.stt.realtime, threshold },
                    },
                  })
                }
              />
              <NumberField
                id="sarvam-vad-silence"
                label="Silence to end a turn, ms"
                value={config.stt.realtime.silence_duration_ms}
                min={1}
                step={50}
                hint="Increase if callers pause mid-sentence; start at 500 ms."
                disabled={disabled}
                onChange={(silence_duration_ms) =>
                  change({
                    ...config,
                    stt: {
                      ...config.stt,
                      realtime: {
                        ...config.stt.realtime,
                        silence_duration_ms,
                      },
                    },
                  })
                }
              />
              <NumberField
                id="sarvam-vad-min-speech"
                label="Minimum speech to count, ms"
                value={config.stt.realtime.min_speech_duration_ms}
                min={1}
                step={25}
                hint="Increase to ignore short noises; start at 250 ms."
                disabled={disabled}
                onChange={(min_speech_duration_ms) =>
                  change({
                    ...config,
                    stt: {
                      ...config.stt,
                      realtime: {
                        ...config.stt.realtime,
                        min_speech_duration_ms,
                      },
                    },
                  })
                }
              />
              <NumberField
                id="sarvam-vad-prefix-padding"
                label="Audio before speech, ms"
                value={config.stt.realtime.prefix_padding_ms ?? 0}
                min={0}
                step={20}
                hint="Increase if the first syllable is clipped; 0 keeps Sarvam's default."
                disabled={disabled}
                onChange={(value) =>
                  change({
                    ...config,
                    stt: {
                      ...config.stt,
                      realtime: {
                        ...config.stt.realtime,
                        prefix_padding_ms: value || null,
                      },
                    },
                  })
                }
              />
              <Field>
                <FieldLabel>Endpointing</FieldLabel>
                <FieldDescription>
                  Sarvam server VAD controls turn boundaries. Realtime uses a
                  local Silero VAD analyzer for Pipecat timing and TTFB. Smart
                  Turn is bypassed because Sarvam supplies external turn
                  boundaries.
                </FieldDescription>
              </Field>
            </>
          ) : (
            <>
              <NumberField
                id="vad-confidence"
                label="VAD confidence"
                value={config.vad.confidence}
                min={0}
                max={1}
                step={0.05}
                disabled={disabled}
                onChange={(confidence) =>
                  change({ ...config, vad: { ...config.vad, confidence } })
                }
              />
              <NumberField
                id="vad-start"
                label="Speech start, seconds"
                value={config.vad.start_secs}
                min={0.01}
                step={0.05}
                disabled={disabled}
                onChange={(start_secs) =>
                  change({ ...config, vad: { ...config.vad, start_secs } })
                }
              />
              <NumberField
                id="vad-stop"
                label="Speech stop, seconds"
                value={config.vad.stop_secs}
                min={0.01}
                step={0.05}
                disabled={disabled}
                onChange={(stop_secs) =>
                  change({ ...config, vad: { ...config.vad, stop_secs } })
                }
              />
              <NumberField
                id="vad-volume"
                label="Minimum volume"
                value={config.vad.min_volume}
                min={0}
                max={1}
                step={0.05}
                disabled={disabled}
                onChange={(min_volume) =>
                  change({ ...config, vad: { ...config.vad, min_volume } })
                }
              />
            </>
          )}
        </FieldGroup>
        <ReadOnlyValue label="Channels" value={config.audio.channels} />
        <ReadOnlyValue label="Encoding" value={config.audio.encoding} />
        <ReadOnlyValue
          label="Frame"
          value={`${config.audio.frame_ms} ms`}
          reason="Fixed by current runtime contract."
        />
      </div>
      <div className="flex flex-col gap-4">
        <h2 className="text-base font-semibold">Call limits</h2>
        <FieldGroup>
          <NumberField
            id="max-duration"
            label="Maximum duration, seconds"
            value={config.call_limits.max_duration_secs}
            min={1}
            disabled={disabled}
            onChange={(max_duration_secs) =>
              change({
                ...config,
                call_limits: { ...config.call_limits, max_duration_secs },
              })
            }
          />
          <NumberField
            id="idle-timeout"
            label="Idle timeout, seconds"
            value={config.call_limits.idle_timeout_secs}
            min={1}
            disabled={disabled}
            onChange={(idle_timeout_secs) =>
              change({
                ...config,
                call_limits: { ...config.call_limits, idle_timeout_secs },
              })
            }
          />
          <Field>
            <FieldLabel htmlFor="interruptions">Interruptions</FieldLabel>
            <NativeSelect
              id="interruptions"
              value={String(config.call_limits.interruptions_enabled)}
              disabled={disabled}
              onChange={(event) =>
                change({
                  ...config,
                  call_limits: {
                    ...config.call_limits,
                    interruptions_enabled: event.target.value === "true",
                  },
                })
              }
            >
              <option value="true">Enabled</option>
              <option value="false">Disabled</option>
            </NativeSelect>
          </Field>
        </FieldGroup>
        <p className="text-xs text-muted-foreground">
          Interruptions control barge-in; the idle timeout starts after the agent
          finishes speaking, reprompts once, then ends the call after another idle
          period. Verify thresholds on a real carrier call.
        </p>
      </div>
    </section>
  );
}
