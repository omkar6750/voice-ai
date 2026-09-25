import { ReadOnlyValue } from "@/components/record-page";
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { NumberField } from "./ConfigFields";
import type { AgentConfig, ProviderCatalog } from "./types";

export function ModelsPanel({
  config,
  change,
  catalog,
  disabled,
}: {
  config: AgentConfig;
  change: (next: AgentConfig) => void;
  catalog: ProviderCatalog | null;
  disabled: boolean;
}) {
  const groqModels =
    catalog?.providers.find(
      (provider) =>
        provider.provider === "groq" && provider.slots.includes("llm"),
    )?.models ?? [];
  const modelListed = groqModels.includes(config.llm.model);
  return (
    <section className="grid max-w-5xl gap-8 lg:grid-cols-2">
      <div className="flex flex-col gap-4">
        <h2 className="text-base font-semibold">Language model</h2>
        <FieldGroup>
          <Field>
            <FieldLabel htmlFor="llm-model">Groq model</FieldLabel>
            <NativeSelect
              id="llm-model"
              value={config.llm.model}
              disabled={disabled || !catalog}
              onChange={(event) =>
                change({
                  ...config,
                  llm: { ...config.llm, model: event.target.value },
                })
              }
            >
              {!modelListed && (
                <option value={config.llm.model}>
                  {config.llm.model} (stored)
                </option>
              )}
              {groqModels.map((model) => (
                <option key={model} value={model}>
                  {model}
                </option>
              ))}
            </NativeSelect>
            <FieldDescription>
              Options from backend provider catalog. Catalog does not confirm
              credentials or runtime readiness.
            </FieldDescription>
          </Field>
          <NumberField
            id="llm-temperature"
            label="Temperature"
            value={config.llm.temperature}
            min={0}
            max={2}
            step={0.1}
            disabled={disabled}
            onChange={(temperature) =>
              change({ ...config, llm: { ...config.llm, temperature } })
            }
          />
          <NumberField
            id="llm-max-tokens"
            label="Maximum output tokens"
            value={config.llm.max_tokens}
            min={1}
            disabled={disabled}
            onChange={(max_tokens) =>
              change({ ...config, llm: { ...config.llm, max_tokens } })
            }
          />
          <Field>
            <FieldLabel htmlFor="llm-top-p">Top-p (optional)</FieldLabel>
            <Input
              id="llm-top-p"
              type="number"
              min={0.01}
              max={1}
              step={0.01}
              value={config.llm.top_p ?? ""}
              placeholder="Provider default"
              disabled={disabled}
              onChange={(event) =>
                change({
                  ...config,
                  llm: {
                    ...config.llm,
                    top_p:
                      event.target.value === ""
                        ? null
                        : Number(event.target.value),
                  },
                })
              }
            />
          </Field>
        </FieldGroup>
        <ReadOnlyValue label="Provider" value={config.llm.provider} />
        <ReadOnlyValue
          label="Reasoning effort"
          value={config.llm.reasoning_effort}
          reason="Current runtime contract supports none only."
        />
      </div>
      <div className="flex flex-col gap-4">
        <h2 className="text-base font-semibold">Speech services</h2>
        <div>
          <h3 className="text-sm font-medium">Speech recognition</h3>
          <ReadOnlyValue label="Provider" value={config.stt.provider} />
          <ReadOnlyValue
            label="Model"
            value={config.stt.model}
            reason="Backend contract currently fixes Sarvam saaras:v3."
          />
        </div>
        <div>
          <h3 className="text-sm font-medium">Speech synthesis</h3>
          <ReadOnlyValue label="Provider" value={config.tts.provider} />
          <ReadOnlyValue label="Model" value={config.tts.model} />
          <ReadOnlyValue
            label="Voice ID"
            value={config.tts.voice}
            reason="Voice catalog API is missing. No invented voice choices."
          />
          <ReadOnlyValue label="Language" value={config.tts.language} />
          <ReadOnlyValue label="Pace" value={config.tts.pace} />
        </div>
      </div>
    </section>
  );
}
