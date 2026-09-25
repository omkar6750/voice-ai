import { ReadOnlyValue } from "@/components/record-page";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { NumberField } from "./ConfigFields";
import type { AgentConfig, ProviderCatalog } from "./types";

export function ModelsPanel({
  config, change, catalog, disabled,
}: {
  config: AgentConfig;
  change: (next: AgentConfig) => void;
  catalog: ProviderCatalog | null;
  disabled: boolean;
}) {
  const llmProviders = catalog?.providers.filter((provider) => provider.slots.includes("llm")) ?? [];
  const selectedLlm = llmProviders.find((provider) => provider.provider === config.llm.provider);
  const llmModels = selectedLlm?.models_by_slot?.llm ?? selectedLlm?.models ?? [];
  const modelListed = llmModels.includes(config.llm.model);

  const ttsProviders = catalog?.providers.filter((provider) => provider.slots.includes("tts")) ?? [];
  const selectedTts = ttsProviders.find((provider) => provider.provider === config.tts.provider);
  const ttsModels = selectedTts?.models_by_slot?.tts ?? ["bulbul:v3"];
  const ttsLanguages = ["en-IN", "hi-IN"];

  return (
    <section className="grid max-w-5xl gap-8 lg:grid-cols-2">
      <div className="flex flex-col gap-4">
        <h2 className="text-base font-semibold">Language model</h2>
        <FieldGroup>
          <Field>
            <FieldLabel htmlFor="llm-provider">Provider</FieldLabel>
            <NativeSelect id="llm-provider" className="w-full" value={config.llm.provider} disabled={disabled || !catalog} onChange={(event) => {
              const provider = event.target.value as "groq" | "gemini";
              const choice = llmProviders.find((item) => item.provider === provider);
              const available = choice?.models_by_slot?.llm ?? choice?.models ?? [];
              if (!available.length) return;
              change({ ...config, llm: {
                ...config.llm, provider, model: available[0],
                reasoning_effort: provider === "gemini" ? "provider_default" : "none",
              } });
            }}>
              {llmProviders.map((item) => {
                const available = item.models_by_slot?.llm ?? item.models;
                return (
                  <option key={item.provider} value={item.provider} disabled={!available.length}>
                    {item.provider}{!available.length ? ` (${item.status ?? "unavailable"})` : ""}
                  </option>
                );
              })}
            </NativeSelect>
            <FieldDescription>Provider credentials are configured by the developer, not in this dashboard.</FieldDescription>
          </Field>
          <Field>
            <FieldLabel htmlFor="llm-model">Model</FieldLabel>
            <NativeSelect id="llm-model" className="w-full" value={config.llm.model} disabled={disabled || !catalog || llmModels.length === 0} onChange={(event) => change({ ...config, llm: { ...config.llm, model: event.target.value } })}>
              {!modelListed && <option value={config.llm.model}>{config.llm.model} (stored)</option>}
              {llmModels.map((model) => <option key={model} value={model}>{model}</option>)}
            </NativeSelect>
            <FieldDescription>Catalog status: {selectedLlm?.status ?? "configured"}. Segmented to LLM chat models only.</FieldDescription>
          </Field>
          <NumberField id="llm-temperature" label="Temperature" value={config.llm.temperature} min={0} max={2} step={0.1} disabled={disabled} onChange={(temperature) => change({ ...config, llm: { ...config.llm, temperature } })} />
          <NumberField id="llm-max-tokens" label="Maximum output tokens" value={config.llm.max_tokens} min={1} disabled={disabled} onChange={(max_tokens) => change({ ...config, llm: { ...config.llm, max_tokens } })} />
          <Field>
            <FieldLabel htmlFor="llm-top-p">Top-p (optional)</FieldLabel>
            <Input id="llm-top-p" type="number" min={0.01} max={1} step={0.01} value={config.llm.top_p ?? ""} placeholder="Provider default" disabled={disabled} onChange={(event) => change({ ...config, llm: { ...config.llm, top_p: event.target.value === "" ? null : Number(event.target.value) } })} />
          </Field>
        </FieldGroup>
        <ReadOnlyValue label="Reasoning" value={config.llm.reasoning_effort} reason="Groq reasoning disabled; Gemini uses its model default. No universal off switch exists." />
      </div>

      <div className="flex flex-col gap-4">
        <h2 className="text-base font-semibold">Speech services</h2>
        <div>
          <h3 className="text-sm font-medium">Speech recognition</h3>
          <ReadOnlyValue label="Provider" value={config.stt.provider} />
          <ReadOnlyValue label="Model" value={config.stt.model} reason="Backend contract currently fixes Sarvam saaras:v3." />
        </div>

        <div className="flex flex-col gap-4 pt-2">
          <h3 className="text-sm font-medium">Speech synthesis</h3>
          <FieldGroup>
            <Field>
              <FieldLabel htmlFor="tts-provider">TTS Provider</FieldLabel>
              <NativeSelect
                id="tts-provider"
                className="w-full"
                value={config.tts.provider}
                disabled={disabled}
                onChange={(event) => {
                  const provider = event.target.value as "sarvam" | "cartesia";
                  const choice = ttsProviders.find((item) => item.provider === provider);
                  const defaultVoice = choice?.voices?.[0]?.id ?? (provider === "sarvam" ? "shubh" : "sonic-3");
                  const defaultModel = choice?.models_by_slot?.tts?.[0] ?? (provider === "sarvam" ? "bulbul:v3" : "sonic-3");
                  change({
                    ...config,
                    tts: {
                      ...config.tts,
                      provider,
                      model: defaultModel,
                      voice: defaultVoice,
                    },
                  });
                }}
              >
                <option value="sarvam">Sarvam AI</option>
                <option value="cartesia">Cartesia</option>
              </NativeSelect>
            </Field>

            <Field>
              <FieldLabel htmlFor="tts-model">TTS Model</FieldLabel>
              <NativeSelect
                id="tts-model"
                className="w-full"
                value={config.tts.model}
                disabled={disabled || ttsModels.length <= 1}
                onChange={(event) => change({ ...config, tts: { ...config.tts, model: event.target.value } })}
              >
                {ttsModels.map((model) => (
                  <option key={model} value={model}>{model}</option>
                ))}
              </NativeSelect>
            </Field>

            <Field>
              <FieldLabel htmlFor="tts-voice">Voice</FieldLabel>
              <Input
                id="tts-voice"
                value={config.tts.voice}
                disabled={disabled}
                onChange={(event) => change({ ...config, tts: { ...config.tts, voice: event.target.value } })}
              />
              <FieldDescription>Enter a voice supported by your configured provider.</FieldDescription>
            </Field>

            {config.tts.provider === "sarvam" && (
              <Field>
                <FieldLabel htmlFor="tts-language">Language</FieldLabel>
                <NativeSelect
                  id="tts-language"
                  className="w-full"
                  value={config.tts.language}
                  disabled={disabled}
                  onChange={(event) => change({ ...config, tts: { ...config.tts, language: event.target.value } })}
                >
                  {ttsLanguages.map((lang) => (
                    <option key={lang} value={lang}>{lang}</option>
                  ))}
                </NativeSelect>
              </Field>
            )}

            <NumberField
              id="tts-pace"
              label="Pace"
              value={config.tts.pace}
              min={0.5}
              max={2.0}
              step={0.05}
              disabled={disabled}
              onChange={(pace) => change({ ...config, tts: { ...config.tts, pace } })}
            />
          </FieldGroup>
        </div>
      </div>
    </section>
  );
}
