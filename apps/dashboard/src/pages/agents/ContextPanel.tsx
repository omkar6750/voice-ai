import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { SearchableSelect } from "@/components/ui/searchable-select";
import { Textarea } from "@/components/ui/textarea";
import { NumberField } from "./ConfigFields";
import {
  CredentialBindingSelect,
  bindCredential,
} from "./CredentialBindingSelect";
import { OpenRouterModelPicker } from "./OpenRouterModelPicker";
import type { AgentConfig, ProviderCatalog, SummarizerConfig } from "./types";

export function ContextPanel({
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
  const summarizer = config.context.summarizer ?? {};
  const summaryModel: NonNullable<typeof summarizer.model> =
    summarizer.model ?? {
      provider: "groq" as const,
      model: "qwen/qwen3.8-27b",
      temperature: 0.4,
      max_tokens: 512,
      top_p: null,
      reasoning_effort: "none" as const,
      prompt:
        "Summarize the supplied history faithfully; preserve decisions and facts.",
      output_fields: {},
      max_output_tokens: 512,
    };
  const llmProviders =
    catalog?.providers.filter((provider) => provider.slots.includes("llm")) ??
    [];
  const selectedProvider = llmProviders.find(
    (provider) => provider.provider === summaryModel.provider,
  );
  const llmModels =
    selectedProvider?.models_by_slot?.llm ?? selectedProvider?.models ?? [];
  function updateSummarizer(partial: Partial<SummarizerConfig>) {
    change({
      ...config,
      context: {
        ...config.context,
        summarizer: {
          ...summarizer,
          ...partial,
        },
      },
    });
  }

  function updateSummaryModel(
    partial: Partial<NonNullable<SummarizerConfig["model"]>>,
    clearCredential = false,
  ) {
    const next = {
      ...config,
      context: {
        ...config.context,
        summarizer: { ...summarizer, model: { ...summaryModel, ...partial } },
      },
    };
    change(clearCredential ? bindCredential(next, "summarizer", null) : next);
  }

  return (
    <div className="grid max-w-5xl gap-8 lg:grid-cols-2">
      <div className="flex flex-col gap-6">
        <div>
          <h2 className="text-base font-semibold">Context window</h2>
          <p className="text-xs text-muted-foreground">
            Live calls use Pipecat's native context summarizer when enabled.
          </p>
        </div>

        <FieldGroup>
          <div className="grid grid-cols-2 gap-4">
            <NumberField
              id="context-window"
              label="Context window (tokens)"
              value={summarizer.context_window_tokens ?? 8192}
              min={1024}
              max={128000}
              step={1024}
              disabled={disabled}
              onChange={(val) =>
                updateSummarizer({ context_window_tokens: val })
              }
              hint="Total model context window"
            />
            <NumberField
              id="unsummarized-msgs"
              label="Every N exchanges"
              value={summarizer.every_n_exchanges ?? 10}
              min={1}
              max={50}
              disabled={disabled}
              onChange={(val) => updateSummarizer({ every_n_exchanges: val })}
              hint="Completed caller/agent exchanges before compaction"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <NumberField
              id="preserve-recent"
              label="Preserve recent msgs"
              value={summarizer.preserve_recent_messages ?? 6}
              min={0}
              max={50}
              disabled={disabled}
              onChange={(val) =>
                updateSummarizer({ preserve_recent_messages: val })
              }
              hint="Recent messages kept uncompacted"
            />
            <NumberField
              id="summary-output"
              label="Summary output tokens"
              value={summarizer.output_budget_tokens ?? 512}
              min={64}
              max={2048}
              disabled={disabled}
              onChange={(val) =>
                updateSummarizer({ output_budget_tokens: val })
              }
              hint="Maximum generated summary size"
            />
          </div>
        </FieldGroup>
      </div>

      <div className="flex flex-col gap-6">
        <div>
          <h2 className="text-base font-semibold">Summarizer settings</h2>
          <p className="text-xs text-muted-foreground">
            These settings are applied by the live Pipecat runtime.
          </p>
        </div>

        <FieldGroup>
          <Field>
            <FieldLabel htmlFor="summarizer-enabled">
              Summarizer status
            </FieldLabel>
            <NativeSelect
              id="summarizer-enabled"
              value={summarizer.enabled ? "enabled" : "disabled"}
              disabled={disabled}
              onChange={(e) =>
                updateSummarizer({ enabled: e.target.value === "enabled" })
              }
            >
              <option value="disabled">Disabled</option>
              <option value="enabled">Enabled</option>
            </NativeSelect>
          </Field>
          {summarizer.enabled && (
            <CredentialBindingSelect
              stage="summarizer"
              provider={summaryModel.provider}
              value={config.credential_refs.summarizer}
              disabled={disabled}
              change={(id) => change(bindCredential(config, "summarizer", id))}
            />
          )}

          <Field>
            <FieldLabel htmlFor="summary-provider">
              Summary LLM provider
            </FieldLabel>
            <NativeSelect
              id="summary-provider"
              className="w-full"
              value={summaryModel.provider}
              disabled={disabled || !catalog}
              onChange={(event) => {
                const provider = event.target.value as NonNullable<
                  typeof summaryModel
                >["provider"];
                const selected = llmProviders.find(
                  (item) => item.provider === provider,
                );
                const models =
                  selected?.models_by_slot?.llm ?? selected?.models ?? [];
                if (!models.length && provider !== "openrouter") return;
                updateSummaryModel({
                  provider,
                  model: models[0] ?? summaryModel.model,
                  reasoning_effort:
                    provider === "isoquant"
                      ? "low"
                      : provider === "gemini" || provider === "openrouter"
                      ? "provider_default"
                      : "none",
                  models: provider === "openrouter" ? summaryModel.models : [],
                  provider_preferences:
                    provider === "openrouter" ? summaryModel.provider_preferences : null,
                }, true);
              }}
            >
              {llmProviders.map((item) => {
                const models = item.models_by_slot?.llm ?? item.models ?? [];
                return (
                  <option
                    key={item.provider}
                    value={item.provider}
                    disabled={!models.length && item.provider !== "openrouter"}
                  >
                    {item.provider}
                    {!models.length && item.provider !== "openrouter"
                      ? ` (${item.status ?? "unavailable"})`
                      : ""}
                  </option>
                );
              })}
            </NativeSelect>
            <FieldDescription>
              Uses the selected provider with server-side credentials.
            </FieldDescription>
          </Field>

          {summaryModel.provider === "openrouter" ? (
            <OpenRouterModelPicker
              stage="summarizer"
              credentialId={config.credential_refs.summarizer}
              value={summaryModel.model ?? ""}
              disabled={disabled}
              onChange={(model) => updateSummaryModel({ model })}
            />
          ) : (
            <Field>
              <FieldLabel htmlFor="summary-model">Summary model</FieldLabel>
              <SearchableSelect
                id="summary-model"
                value={summaryModel.model ?? ""}
                onChange={(model) => updateSummaryModel({ model })}
                options={[
                  ...(!llmModels.includes(summaryModel.model ?? "")
                    ? [
                        {
                          value: summaryModel.model ?? "",
                          label: `${summaryModel.model} (saved)`,
                        },
                      ]
                    : []),
                  ...llmModels.map((model) => ({ value: model, label: model })),
                ]}
                selectionOnly
                disabled={disabled || !catalog || !llmModels.length}
                placeholder="Search models..."
              />
            </Field>
          )}
          <div className="grid grid-cols-2 gap-4">
            <NumberField
              id="summary-temperature"
              label="Temperature"
              value={summaryModel.temperature ?? 0.4}
              min={0}
              max={2}
              step={0.1}
              disabled={disabled}
              onChange={(temperature) => updateSummaryModel({ temperature })}
            />
            <NumberField
              id="summary-max-tokens"
              label="Maximum output tokens"
              value={summaryModel.max_tokens ?? 512}
              min={1}
              disabled={disabled}
              onChange={(max_tokens) => updateSummaryModel({ max_tokens })}
            />
          </div>
          <Field>
            <FieldLabel htmlFor="summary-top-p">Top-p (optional)</FieldLabel>
            <Input
              id="summary-top-p"
              type="number"
              min={0.01}
              max={1}
              step={0.01}
              value={summaryModel.top_p ?? ""}
              placeholder="Provider default"
              disabled={disabled}
              onChange={(event) =>
                updateSummaryModel({
                  top_p:
                    event.target.value === ""
                      ? null
                      : Number(event.target.value),
                })
              }
            />
            <FieldDescription>
              Reasoning: {summaryModel.reasoning_effort ?? "none"}{" "}
              (provider-constrained).
            </FieldDescription>
          </Field>

          <Field>
            <FieldLabel htmlFor="summarizer-prompt">
              Summarizer instructions
            </FieldLabel>
            <Textarea
              id="summarizer-prompt"
              rows={4}
              value={summarizer.prompt ?? ""}
              disabled={disabled}
              onChange={(e) => updateSummarizer({ prompt: e.target.value })}
              placeholder="Summarize the supplied history faithfully; preserve decisions and facts."
            />
            <FieldDescription>
              Instructions guiding model summary generation
            </FieldDescription>
          </Field>
        </FieldGroup>

        <div className="rounded-md border p-3 text-xs text-muted-foreground">
          <p className="font-medium text-foreground">
            Summary Evidence Retention
          </p>
          <p className="mt-1">
            Summaries are applied asynchronously by Pipecat and preserve the
            configured recent messages. A slow or failed summary leaves the
            current context unchanged.
          </p>
        </div>
      </div>
    </div>
  );
}
