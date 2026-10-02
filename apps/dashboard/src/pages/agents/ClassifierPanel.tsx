import { BrainCircuit, Cpu, Sparkles } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import {
  NativeSelect,
  NativeSelectOption,
} from "@/components/ui/native-select";
import { SearchableSelect } from "@/components/ui/searchable-select";
import { NumberField } from "./ConfigFields";
import {
  CredentialBindingSelect,
  bindCredential,
} from "./CredentialBindingSelect";
import { OpenRouterModelPicker } from "./OpenRouterModelPicker";
import type { AgentConfig, ProviderCatalog } from "./types";

export function ClassifierPanel({
  config,
  change,
  providers,
  disabled,
}: {
  config: AgentConfig;
  change: (next: AgentConfig) => void;
  providers?: ProviderCatalog | null;
  disabled: boolean;
}) {
  const contract = providers?.classifier_contract;
  const classifier = config.classifier;
  const classifierType = classifier.classifier_type ?? "llm";
  const currentLlm: NonNullable<typeof classifier.llm> = classifier.llm ?? {
    provider: "groq",
    model: "qwen/qwen3.8-27b",
    temperature: 0.2,
    max_tokens: 256,
    top_p: null,
    reasoning_effort: "none",
    models: [],
    provider_preferences: null,
    prompt: "",
    output_fields: {},
    max_output_tokens: 256,
  };
  const allNodeIds = config.flow.nodes.map((node) => node.id);

  function update(partial: Partial<typeof classifier>) {
    change({
      ...config,
      classifier: {
        ...classifier,
        ...partial,
      },
    });
  }

  function toggleNode(listKey: "node_entries" | "node_exits", nodeId: string) {
    const current = classifier[listKey] ?? [];
    const next = current.includes(nodeId)
      ? current.filter((id) => id !== nodeId)
      : [...current, nodeId];
    update({ [listKey]: next });
  }

  const llmProviders =
    providers?.providers.filter(
      (p) =>
        p.slots.includes("llm") || (p.models_by_slot?.llm?.length ?? 0) > 0,
    ) ?? [];

  const currentProvider = classifier.llm?.provider || "groq";
  const selectedProviderEntry = llmProviders.find(
    (p) => p.provider === currentProvider,
  );
  const availableModels =
    selectedProviderEntry?.models_by_slot?.llm ||
    selectedProviderEntry?.models ||
    [];

  return (
    <div className="flex flex-col gap-8 max-w-5xl">
      {/* Top Switcher: Two Choice Boxes */}
      <div className="flex flex-col gap-3">
        <div>
          <h2 className="text-base font-semibold">Classification Engine</h2>
          <p className="text-xs text-muted-foreground">
            Select one classifier mode for this agent. Each engine operates as a
            backend for the same fixed classify_lead tool.
          </p>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {/* Option 1: LLM Classifier */}
          <div
            onClick={() => !disabled && update({ classifier_type: "llm" })}
            className={`cursor-pointer rounded-lg border-2 p-4 transition-all ${
              classifierType === "llm"
                ? "border-primary bg-primary/5 shadow-sm"
                : "border-border hover:border-muted-foreground/40 bg-card"
            }`}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-center gap-2">
                <div
                  className={`rounded-md p-2 ${
                    classifierType === "llm"
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted text-muted-foreground"
                  }`}
                >
                  <Sparkles className="size-4" />
                </div>
                <div>
                  <h3 className="text-sm font-semibold">LLM Classifier</h3>
                  <p className="text-xs text-muted-foreground">
                    Groq / Gemini / OpenRouter / Isoquant
                  </p>
                </div>
              </div>
              <Badge
                variant={classifierType === "llm" ? "default" : "outline"}
                className="text-[11px]"
              >
                {classifierType === "llm" ? "Active" : "Select"}
              </Badge>
            </div>
            <p className="mt-3 text-xs text-muted-foreground">
              Standard LLM prompt-driven classification returning compact
              key-value JSON state through{" "}
              <code className="font-mono text-foreground font-semibold">
                classify_lead
              </code>
              .
            </p>
          </div>

          {/* Option 2: Dedicated Classifier Model (Jev) */}
          <div
            onClick={() => !disabled && update({ classifier_type: "jev" })}
            className={`cursor-pointer rounded-lg border-2 p-4 transition-all ${
              classifierType === "jev"
                ? "border-primary bg-primary/5 shadow-sm"
                : "border-border hover:border-muted-foreground/40 bg-card"
            }`}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-center gap-2">
                <div
                  className={`rounded-md p-2 ${
                    classifierType === "jev"
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted text-muted-foreground"
                  }`}
                >
                  <Cpu className="size-4" />
                </div>
                <div>
                  <h3 className="text-sm font-semibold">Classifier Model</h3>
                  <p className="text-xs text-muted-foreground">
                    TypeSafe AI Jev System One
                  </p>
                </div>
              </div>
              <Badge
                variant={classifierType === "jev" ? "default" : "outline"}
                className="text-[11px]"
              >
                {classifierType === "jev" ? "Active" : "Select"}
              </Badge>
            </div>
            <p className="mt-3 text-xs text-muted-foreground">
              Dedicated multi-choice classification engine with normalized
              results through{" "}
              <code className="font-mono text-foreground font-semibold">
                classify_lead
              </code>
              .
            </p>
          </div>
        </div>
      </div>

      {/* Main Configuration Grid */}
      <div className="grid gap-8 lg:grid-cols-2">
        {/* Left Column: Common Cadence & Triggers */}
        <div className="flex flex-col gap-6">
          <div>
            <h2 className="text-base font-semibold">Cadence & Triggers</h2>
            <p className="text-xs text-muted-foreground">
              Configure when the selected classifier engine executes during
              calls.
            </p>
          </div>

          <FieldGroup>
            <Field>
              <FieldLabel htmlFor="classifier-enabled">
                Classifier status
              </FieldLabel>
              <NativeSelect
                id="classifier-enabled"
                value={classifier.enabled ? "enabled" : "disabled"}
                disabled={disabled}
                onChange={(e) =>
                  update({ enabled: e.target.value === "enabled" })
                }
              >
                <NativeSelectOption value="enabled">Enabled</NativeSelectOption>
                <NativeSelectOption value="disabled">
                  Disabled
                </NativeSelectOption>
              </NativeSelect>
            </Field>

            <Field>
              <FieldLabel>Node entry triggers</FieldLabel>
              <FieldDescription>
                Trigger evaluation immediately upon entering any selected flow
                node:
              </FieldDescription>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {allNodeIds.map((id) => {
                  const active = (classifier.node_entries ?? []).includes(id);
                  return (
                    <Badge
                      key={id}
                      variant={active ? "default" : "outline"}
                      className="cursor-pointer select-none"
                      onClick={() =>
                        !disabled && toggleNode("node_entries", id)
                      }
                    >
                      {id}
                    </Badge>
                  );
                })}
              </div>
            </Field>

            <Field>
              <FieldLabel>Node exit triggers</FieldLabel>
              <FieldDescription>
                Trigger evaluation when transitioning away from any selected
                flow node:
              </FieldDescription>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {allNodeIds.map((id) => {
                  const active = (classifier.node_exits ?? []).includes(id);
                  return (
                    <Badge
                      key={id}
                      variant={active ? "default" : "outline"}
                      className="cursor-pointer select-none"
                      onClick={() => !disabled && toggleNode("node_exits", id)}
                    >
                      {id}
                    </Badge>
                  );
                })}
              </div>
            </Field>

            <div className="grid grid-cols-2 gap-4">
              <NumberField
                id="classifier-every-n"
                label="Every N exchanges"
                value={classifier.every_n_exchanges ?? 0}
                min={0}
                max={50}
                disabled={disabled}
                onChange={(val) =>
                  update({ every_n_exchanges: val > 0 ? val : null })
                }
                hint="Runs after each N completed caller exchanges"
              />
            </div>
          </FieldGroup>
        </div>

        {/* Right Column: Engine-Specific Form */}
        <div className="flex flex-col gap-6">
          {classifierType === "llm" ? (
            /* LLM CLASSIFIER FORM */
            <>
              <div>
                <h2 className="text-base font-semibold">
                  LLM Classifier Settings
                </h2>
                <p className="text-xs text-muted-foreground">
                  Select the LLM powering the fixed{" "}
                  <code className="font-mono">classify_lead</code> tool.
                </p>
              </div>

              <FieldGroup>
                <div className="grid grid-cols-2 gap-4">
                  <Field>
                    <FieldLabel htmlFor="classifier-provider">
                      Model provider
                    </FieldLabel>
                    <NativeSelect
                      id="classifier-provider"
                      value={currentProvider}
                      disabled={disabled}
                      onChange={(e) => {
                        const provider = e.target
                          .value as typeof currentLlm.provider;
                        const next = {
                          ...config,
                          classifier: {
                            ...classifier,
                            llm: {
                              ...currentLlm,
                              provider,
                              model:
                                providers?.providers.find(
                                  (p) => p.provider === provider,
                                )?.models_by_slot?.llm?.[0] || "",
                              reasoning_effort:
                                provider === "isoquant"
                                  ? ("low" as const)
                                  : provider === "gemini" ||
                                      provider === "openrouter"
                                    ? ("provider_default" as const)
                                    : ("none" as const),
                              models:
                                provider === "openrouter"
                                  ? currentLlm.models
                                  : [],
                              provider_preferences:
                                provider === "openrouter"
                                  ? currentLlm.provider_preferences
                                  : null,
                            },
                          },
                        };
                        change(bindCredential(next, "classifier", null));
                      }}
                    >
                      {llmProviders.map((p) => (
                        <NativeSelectOption key={p.provider} value={p.provider}>
                          {p.provider}
                        </NativeSelectOption>
                      ))}
                    </NativeSelect>
                  </Field>

                  {currentProvider === "openrouter" ? (
                    <OpenRouterModelPicker
                      stage="classifier"
                      credentialId={config.credential_refs.classifier}
                      value={currentLlm.model || ""}
                      disabled={disabled}
                      onChange={(model) =>
                        update({ llm: { ...currentLlm, model } })
                      }
                    />
                  ) : (
                    <Field>
                      <FieldLabel htmlFor="classifier-model">Model</FieldLabel>
                      <SearchableSelect
                        id="classifier-model"
                        value={currentLlm.model || availableModels[0] || ""}
                        onChange={(model) =>
                          update({ llm: { ...currentLlm, model } })
                        }
                        options={[
                          ...(!availableModels.includes(currentLlm.model || "")
                            ? [
                                {
                                  value:
                                    currentLlm.model ||
                                    availableModels[0] ||
                                    "",
                                  label: `${currentLlm.model || availableModels[0] || ""} (saved)`,
                                },
                              ]
                            : []),
                          ...availableModels.map((model) => ({
                            value: model,
                            label: model,
                          })),
                        ]}
                        selectionOnly
                        disabled={disabled || !availableModels.length}
                        placeholder="Search models..."
                      />
                    </Field>
                  )}
                </div>
                <CredentialBindingSelect
                  stage="classifier"
                  provider={currentLlm.provider}
                  value={config.credential_refs.classifier}
                  disabled={disabled}
                  change={(id) =>
                    change(bindCredential(config, "classifier", id))
                  }
                />
              </FieldGroup>
            </>
          ) : (
            /* JEV SYSTEM ONE FORM */
            <>
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-base font-semibold">
                    TypeSafe AI Jev Settings
                  </h2>
                  <p className="text-xs text-muted-foreground">
                    Multi-choice questions and criteria evaluated by the{" "}
                    <code className="font-mono">classify_lead</code> tool.
                  </p>
                </div>
              </div>

              <FieldGroup>
                <CredentialBindingSelect
                  stage="classifier"
                  provider="jev"
                  value={config.credential_refs.classifier}
                  disabled={disabled}
                  change={(id) =>
                    change(bindCredential(config, "classifier", id))
                  }
                />
                <p className="text-sm text-muted-foreground">
                  JEV uses the fixed questions below and jev-latest. Endpoint
                  and answer choices are managed by the application.
                </p>
              </FieldGroup>
            </>
          )}

          <LeadClassifierDetails contract={contract} />
        </div>
      </div>
    </div>
  );
}

export function LeadClassifierDetails({
  contract,
}: {
  contract?: ProviderCatalog["classifier_contract"];
}) {
  return (
    <section className="grid gap-3" aria-label="Fixed classifier contract">
      <h3 className="text-sm font-semibold">
        classify_lead · Fixed contract v1
      </h3>
      <p className="text-xs text-muted-foreground">
        Both engines answer the same three questions. Prompts, criteria and
        output labels are locked. Cadence controls when it runs; tool routing
        controls the next node. Three answers produce 27 possible combinations.
      </p>
      {!contract?.questions ? (
        <p role="alert">
          Classifier contract unavailable. Reload the page to fetch the provider
          catalog.
        </p>
      ) : (
        Object.entries(contract.questions).map(([key, question]) => (
          <section key={key} className="grid gap-2 rounded-lg bg-muted/40 p-3">
            <h4 className="font-mono text-sm font-semibold">{key}</h4>
            <p className="text-xs text-muted-foreground">
              {question.instructions}
            </p>
            <dl className="grid gap-2 text-xs">
              {Object.entries(question.criteria ?? {}).map(
                ([choice, meaning]) => (
                  <div key={choice}>
                    <dt className="font-mono font-semibold">{choice}</dt>
                    <dd className="text-muted-foreground">{meaning}</dd>
                  </div>
                ),
              )}
            </dl>
          </section>
        ))
      )}
      {contract?.prompt && (
        <details>
          <summary className="cursor-pointer text-sm">
            Locked LLM instructions
          </summary>
          <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap rounded-lg bg-muted/40 p-3 text-xs">
            {contract.prompt}
          </pre>
        </details>
      )}
      <p className="text-xs text-muted-foreground">
        Output: lead_temperature, service_fit, tone and classification_key
        (temperature|fit|tone). Existing lead_followup policies additionally
        provide followup_route. Invalid or incomplete answers return an error
        and cannot match a classification case.
      </p>
    </section>
  );
}
