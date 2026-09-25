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
  return (
    <section className="grid max-w-5xl gap-8 lg:grid-cols-2">
      <div className="flex flex-col gap-4">
        <h2 className="text-base font-semibold">Audio and VAD</h2>
        <FieldGroup>
          <Field>
            <FieldLabel htmlFor="sample-rate">
              Input/output sample rate
            </FieldLabel>
            <NativeSelect
              id="sample-rate"
              value={String(config.audio.sample_rate)}
              disabled={disabled}
              onChange={(event) =>
                change({
                  ...config,
                  audio: {
                    ...config.audio,
                    sample_rate: Number(event.target.value) as 8000 | 16000,
                  },
                })
              }
            >
              <option value="8000">8 kHz</option>
              <option value="16000">16 kHz</option>
            </NativeSelect>
            <FieldDescription>
              Validate endpoint audio compatibility before dialing. Configured
              value does not prove modem support.
            </FieldDescription>
          </Field>
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
          VAD and interruption settings are stored. Verify their effect in a
          live call before treating them as proven.
        </p>
      </div>
    </section>
  );
}
