import { ReadOnlyValue } from "@/components/record-page";
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { SearchableSelect } from "@/components/ui/searchable-select";
import { NumberField } from "./ConfigFields";
import {
  CredentialBindingSelect,
  bindCredential,
} from "./CredentialBindingSelect";
import { OpenRouterModelPicker } from "./OpenRouterModelPicker";
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
  const llmProviders =
    catalog?.providers.filter((provider) => provider.slots.includes("llm")) ??
    [];
  const selectedLlm = llmProviders.find(
    (provider) => provider.provider === config.llm.provider,
  );
  const llmModels =
    selectedLlm?.models_by_slot?.llm ?? selectedLlm?.models ?? [];
  const modelListed = llmModels.includes(config.llm.model);

  const sttProviders =
    catalog?.providers.filter((provider) => provider.slots.includes("stt")) ??
    [];
  const selectedStt = sttProviders.find(
    (provider) => provider.provider === config.stt.provider,
  );
  const sttModels = selectedStt?.models_by_slot?.stt ?? [];
  const sttModelListed = sttModels.includes(config.stt.model);

  const ttsProviders =
    catalog?.providers.filter((provider) => provider.slots.includes("tts")) ??
    [];
  const selectedTts = ttsProviders.find(
    (provider) => provider.provider === config.tts.provider,
  );
  const ttsModels = selectedTts?.models_by_slot?.tts ?? [];
  const ttsLanguages = selectedTts?.languages ?? [];
  const ttsVoices = selectedTts?.voices ?? [];
  const ttsField = (name: string) => selectedTts?.fields?.[name];
  const ttsFieldSupported = (name: string) =>
    ttsField(name)?.runtime_supported ?? false;
  const cartesiaGeneration = config.tts.cartesia?.generation_config;
  function updateCartesiaGeneration(
    field: "volume" | "speed" | "emotion",
    value: number | string | null,
  ) {
    change({
      ...config,
      tts: {
        ...config.tts,
        cartesia: {
          ...config.tts.cartesia,
          pronunciation_dict_id:
            config.tts.cartesia?.pronunciation_dict_id ?? null,
          generation_config: {
            volume: cartesiaGeneration?.volume ?? null,
            speed: cartesiaGeneration?.speed ?? null,
            emotion: cartesiaGeneration?.emotion ?? null,
            [field]: value,
          },
        },
      },
    });
  }

  return (
    <section className="grid max-w-5xl gap-8 lg:grid-cols-2">
      <div className="flex flex-col gap-4">
        <h2 className="text-base font-semibold">Language model</h2>
        <FieldGroup>
          <Field>
            <FieldLabel htmlFor="llm-provider">Provider</FieldLabel>
            <NativeSelect
              id="llm-provider"
              className="w-full"
              value={config.llm.provider}
              disabled={disabled || !catalog}
              onChange={(event) => {
                const provider = event.target
                  .value as AgentConfig["llm"]["provider"];
                const choice = llmProviders.find(
                  (item) => item.provider === provider,
                );
                const available =
                  choice?.models_by_slot?.llm ?? choice?.models ?? [];
                if (!available.length && provider !== "openrouter") return;
                change({
                  ...config,
                  llm: {
                    ...config.llm,
                    provider,
                    model: available[0] ?? config.llm.model,
                    reasoning_effort:
                      provider === "gemini" || provider === "openrouter"
                        ? "provider_default"
                        : "none",
                  },
                });
              }}
            >
              {llmProviders.map((item) => {
                const available = item.models_by_slot?.llm ?? item.models;
                return (
                  <option
                    key={item.provider}
                    value={item.provider}
                    disabled={
                      !available.length && item.provider !== "openrouter"
                    }
                  >
                    {item.provider}
                    {!available.length && item.provider !== "openrouter"
                      ? ` (${item.status ?? "unavailable"})`
                      : ""}
                  </option>
                );
              })}
            </NativeSelect>
            <FieldDescription>
              Select the organization-owned credential used by this stage.
            </FieldDescription>
          </Field>
          <CredentialBindingSelect
            stage="llm"
            provider={config.llm.provider}
            value={config.credential_refs.llm}
            disabled={disabled}
            change={(id) => change(bindCredential(config, "llm", id))}
          />
          {config.llm.provider === "openrouter" ? (
            <OpenRouterModelPicker
              stage="llm"
              credentialId={config.credential_refs.llm}
              value={config.llm.model}
              disabled={disabled}
              onChange={(model) =>
                change({ ...config, llm: { ...config.llm, model } })
              }
            />
          ) : (
            <Field>
              <FieldLabel htmlFor="llm-model">Model</FieldLabel>
              <SearchableSelect
                id="llm-model"
                value={config.llm.model}
                onChange={(model) =>
                  change({ ...config, llm: { ...config.llm, model } })
                }
                options={[
                  ...(!modelListed
                    ? [
                        {
                          value: config.llm.model,
                          label: `${config.llm.model} (saved)`,
                        },
                      ]
                    : []),
                  ...llmModels.map((model) => ({ value: model, label: model })),
                ]}
                selectionOnly
                disabled={disabled || !catalog || llmModels.length === 0}
                placeholder="Search models..."
              />
              <FieldDescription>
                Catalog status: {selectedLlm?.status ?? "configured"}. Segmented
                to LLM chat models only.
              </FieldDescription>
            </Field>
          )}
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
        <ReadOnlyValue
          label="Reasoning"
          value={config.llm.reasoning_effort}
          reason="Groq reasoning disabled; Gemini uses its model default. No universal off switch exists."
        />
      </div>

      <div className="flex flex-col gap-4">
        <h2 className="text-base font-semibold">Speech services</h2>
        <div>
          <h3 className="text-sm font-medium">Speech recognition</h3>
          <FieldGroup>
            <Field>
              <FieldLabel htmlFor="stt-provider">STT Provider</FieldLabel>
              <NativeSelect
                id="stt-provider"
                className="w-full"
                value={config.stt.provider}
                disabled={disabled || !catalog}
                onChange={(event) => {
                  const provider = event.target
                    .value as AgentConfig["stt"]["provider"];
                  const choice = sttProviders.find(
                    (item) => item.provider === provider,
                  );
                  const available = choice?.models_by_slot?.stt ?? [];
                  if (!available.length) return;
                  change({
                    ...config,
                    stt: { provider, model: available[0] as "saaras:v3" },
                  });
                }}
              >
                {sttProviders.map((item) => (
                  <option
                    key={item.provider}
                    value={item.provider}
                    disabled={!item.models_by_slot?.stt?.length}
                  >
                    {item.provider}
                    {item.status !== "configured" ? ` (${item.status})` : ""}
                  </option>
                ))}
              </NativeSelect>
              <FieldDescription>
                Choose an organization credential for speech recognition.
              </FieldDescription>
            </Field>
            <CredentialBindingSelect
              stage="stt"
              provider={config.stt.provider}
              value={config.credential_refs.stt}
              disabled={disabled}
              change={(id) => change(bindCredential(config, "stt", id))}
            />
            <Field>
              <FieldLabel htmlFor="stt-model">STT Model</FieldLabel>
              <SearchableSelect
                id="stt-model"
                value={config.stt.model}
                options={[
                  ...(!sttModelListed
                    ? [
                        {
                          value: config.stt.model,
                          label: `${config.stt.model} (saved)`,
                        },
                      ]
                    : []),
                  ...sttModels.map((model) => ({ value: model, label: model })),
                ]}
                selectionOnly
                disabled={disabled || sttModels.length === 0}
                onChange={(model) =>
                  change({
                    ...config,
                    stt: { ...config.stt, model: model as "saaras:v3" },
                  })
                }
                placeholder="Search models..."
              />
              <FieldDescription>
                Catalog status: {selectedStt?.status ?? "unavailable"}.
              </FieldDescription>
            </Field>
          </FieldGroup>
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
                  const provider = event.target
                    .value as AgentConfig["tts"]["provider"];
                  const choice = ttsProviders.find(
                    (item) => item.provider === provider,
                  );
                  const defaultVoice =
                    choice?.voices?.[0]?.id ?? config.tts.voice;
                  const defaultModel =
                    choice?.models_by_slot?.tts?.[0] ?? config.tts.model;
                  change({
                    ...config,
                    tts: {
                      ...config.tts,
                      provider,
                      model: defaultModel,
                      voice: defaultVoice,
                      pace: provider === "cartesia" ? 1 : config.tts.pace,
                      cartesia:
                        provider === "cartesia"
                          ? (config.tts.cartesia ?? null)
                          : null,
                    },
                  });
                }}
              >
                {ttsProviders.map((item) => (
                  <option
                    key={item.provider}
                    value={item.provider}
                    disabled={!item.models_by_slot?.tts?.length}
                  >
                    {item.provider}
                    {item.status !== "configured" ? ` (${item.status})` : ""}
                  </option>
                ))}
              </NativeSelect>
              <FieldDescription>
                Runtime status: {selectedTts?.runtime_status ?? "unavailable"};
                credentials: {selectedTts?.status ?? "unavailable"}.
              </FieldDescription>
            </Field>
            <CredentialBindingSelect
              stage="tts"
              provider={config.tts.provider}
              value={config.credential_refs.tts}
              disabled={disabled}
              change={(id) => change(bindCredential(config, "tts", id))}
            />

            <Field>
              <FieldLabel htmlFor="tts-model">TTS Model</FieldLabel>
              <SearchableSelect
                id="tts-model"
                value={config.tts.model}
                options={[
                  ...(!ttsModels.includes(config.tts.model)
                    ? [
                        {
                          value: config.tts.model,
                          label: `${config.tts.model} (saved)`,
                        },
                      ]
                    : []),
                  ...ttsModels.map((model) => ({ value: model, label: model })),
                ]}
                selectionOnly
                disabled={disabled || ttsModels.length <= 1}
                onChange={(model) =>
                  change({ ...config, tts: { ...config.tts, model } })
                }
                placeholder="Search models..."
              />
            </Field>

            <Field>
              <FieldLabel htmlFor="tts-voice">Voice</FieldLabel>
              {ttsVoices.length ? (
                <NativeSelect
                  id="tts-voice"
                  className="w-full"
                  value={config.tts.voice}
                  disabled={disabled || !ttsFieldSupported("voice")}
                  onChange={(event) =>
                    change({
                      ...config,
                      tts: { ...config.tts, voice: event.target.value },
                    })
                  }
                >
                  {!ttsVoices.some(
                    (voice) => voice.id === config.tts.voice,
                  ) && (
                    <option value={config.tts.voice}>
                      {config.tts.voice} (stored)
                    </option>
                  )}
                  {ttsVoices.map((voice) => (
                    <option key={voice.id} value={voice.id}>
                      {voice.name}
                    </option>
                  ))}
                </NativeSelect>
              ) : (
                <Input
                  id="tts-voice"
                  value={config.tts.voice}
                  disabled={disabled || !ttsFieldSupported("voice")}
                  onChange={(event) =>
                    change({
                      ...config,
                      tts: { ...config.tts, voice: event.target.value },
                    })
                  }
                />
              )}
              <FieldDescription>
                {ttsVoices.length
                  ? "Provider voice catalog."
                  : "Enter a provider voice ID; this provider does not expose a voice catalog."}
              </FieldDescription>
            </Field>

            {ttsFieldSupported("language") && (
              <Field>
                <FieldLabel htmlFor="tts-language">Language</FieldLabel>
                {ttsLanguages.length ? (
                  <NativeSelect
                    id="tts-language"
                    className="w-full"
                    value={config.tts.language}
                    disabled={disabled}
                    onChange={(event) =>
                      change({
                        ...config,
                        tts: { ...config.tts, language: event.target.value },
                      })
                    }
                  >
                    {!ttsLanguages.includes(config.tts.language) && (
                      <option value={config.tts.language}>
                        {config.tts.language} (stored)
                      </option>
                    )}
                    {ttsLanguages.map((lang) => (
                      <option key={lang} value={lang}>
                        {lang}
                      </option>
                    ))}
                  </NativeSelect>
                ) : (
                  <Input
                    id="tts-language"
                    value={config.tts.language}
                    disabled={disabled}
                    onChange={(event) =>
                      change({
                        ...config,
                        tts: { ...config.tts, language: event.target.value },
                      })
                    }
                  />
                )}
              </Field>
            )}

            {config.tts.provider === "sarvam" ? (
              <NumberField
                id="tts-pace"
                label="Pace"
                value={config.tts.pace}
                min={0.5}
                max={2.0}
                step={0.05}
                disabled={disabled}
                onChange={(pace) =>
                  change({ ...config, tts: { ...config.tts, pace } })
                }
              />
            ) : null}
            {config.tts.provider === "cartesia" && (
              <>
                <Field>
                  <FieldLabel htmlFor="cartesia-volume">Volume</FieldLabel>
                  <Input
                    id="cartesia-volume"
                    type="number"
                    min={0.5}
                    max={2}
                    step={0.05}
                    value={cartesiaGeneration?.volume ?? ""}
                    placeholder="Provider default (1.0)"
                    disabled={disabled}
                    onChange={(event) =>
                      updateCartesiaGeneration(
                        "volume",
                        event.target.value === ""
                          ? null
                          : Number(event.target.value),
                      )
                    }
                  />
                  <FieldDescription>
                    Cartesia generation volume, 0.5–2.0.
                  </FieldDescription>
                </Field>
                <Field>
                  <FieldLabel htmlFor="cartesia-speed">Speed</FieldLabel>
                  <Input
                    id="cartesia-speed"
                    type="number"
                    min={0.6}
                    max={1.5}
                    step={0.05}
                    value={cartesiaGeneration?.speed ?? ""}
                    placeholder="Provider default (1.0)"
                    disabled={disabled}
                    onChange={(event) =>
                      updateCartesiaGeneration(
                        "speed",
                        event.target.value === ""
                          ? null
                          : Number(event.target.value),
                      )
                    }
                  />
                  <FieldDescription>
                    Cartesia generation speed, separate from Sarvam pace.
                  </FieldDescription>
                </Field>
                <Field>
                  <FieldLabel htmlFor="cartesia-emotion">Emotion</FieldLabel>
                  <Input
                    id="cartesia-emotion"
                    value={cartesiaGeneration?.emotion ?? ""}
                    placeholder="Provider default"
                    disabled={disabled}
                    onChange={(event) =>
                      updateCartesiaGeneration(
                        "emotion",
                        event.target.value || null,
                      )
                    }
                  />
                  <FieldDescription>
                    For example: calm, excited, or neutral. Voice support
                    varies.
                  </FieldDescription>
                </Field>
                <Field>
                  <FieldLabel htmlFor="cartesia-pronunciation">
                    Pronunciation dictionary ID
                  </FieldLabel>
                  <Input
                    id="cartesia-pronunciation"
                    value={config.tts.cartesia?.pronunciation_dict_id ?? ""}
                    placeholder="Optional dictionary ID"
                    disabled={disabled}
                    onChange={(event) =>
                      change({
                        ...config,
                        tts: {
                          ...config.tts,
                          cartesia: {
                            generation_config:
                              config.tts.cartesia?.generation_config ?? null,
                            pronunciation_dict_id: event.target.value || null,
                          },
                        },
                      })
                    }
                  />
                </Field>
              </>
            )}
          </FieldGroup>
        </div>
      </div>
    </section>
  );
}
