import { Badge } from "@/components/ui/badge";
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import { NumberField } from "./ConfigFields";
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
  const summaryModel = summarizer.model ?? {
    provider: "groq" as const,
    model: "qwen/qwen3.8-27b",
    temperature: 0.4,
    max_tokens: 512,
    top_p: null,
    reasoning_effort: "none" as const,
  };
  const llmProviders = catalog?.providers.filter((provider) => provider.slots.includes("llm")) ?? [];
  const selectedProvider = llmProviders.find((provider) => provider.provider === summaryModel.provider);
  const llmModels = selectedProvider?.models_by_slot?.llm ?? selectedProvider?.models ?? [];
  const allNodeIds = config.flow.nodes.map((node) => node.id);

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

  function updateSummaryModel(partial: NonNullable<SummarizerConfig["model"]>) {
    updateSummarizer({ model: { ...summaryModel, ...partial } });
  }

  function togglePruneNode(nodeId: string) {
    const current = config.context.prune_node_ids ?? [];
    const next = current.includes(nodeId)
      ? current.filter((id) => id !== nodeId)
      : [...current, nodeId];
    change({
      ...config,
      context: {
        ...config.context,
        prune_node_ids: next,
      },
    });
  }

  function parseList(str: string): string[] {
    return str
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
  }

  return (
    <div className="grid max-w-5xl gap-8 lg:grid-cols-2">
      <div className="flex flex-col gap-6">
        <div>
          <h2 className="text-base font-semibold">Context pruning & window</h2>
          <p className="text-xs text-muted-foreground">
            These pruning controls are saved for future work; live calls do not apply them yet.
          </p>
        </div>

        <FieldGroup>
          <Field>
            <FieldLabel>Pruned flow nodes</FieldLabel>
            <FieldDescription>
              Planned only: node-specific transcript pruning is not active in live calls.
            </FieldDescription>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {allNodeIds.map((id) => {
                const active = (config.context.prune_node_ids ?? []).includes(id);
                return (
                  <Badge
                    key={id}
                    variant={active ? "default" : "outline"}
                    className="cursor-pointer select-none"
                    onClick={() => !disabled && togglePruneNode(id)}
                  >
                    {id}
                  </Badge>
                );
              })}
            </div>
          </Field>

          <Field>
            <FieldLabel htmlFor="prune-transitions">Remove transition tool pairs</FieldLabel>
            <NativeSelect
              id="prune-transitions"
              value={config.context.remove_transition_tool_pairs ? "yes" : "no"}
              disabled={disabled}
              onChange={(e) =>
                change({
                  ...config,
                  context: {
                    ...config.context,
                    remove_transition_tool_pairs: e.target.value === "yes",
                  },
                })
              }
            >
              <option value="yes">Yes (omit node-change tool messages)</option>
              <option value="no">No (retain tool calls in context)</option>
            </NativeSelect>
            <FieldDescription>
              Planned only: transition tool-pair removal is not active in live calls.
            </FieldDescription>
          </Field>

          <div className="grid grid-cols-2 gap-4">
            <NumberField
              id="context-window"
              label="Context window (tokens)"
              value={summarizer.context_window_tokens ?? 8192}
              min={1024}
              max={128000}
              step={1024}
              disabled={disabled}
              onChange={(val) => updateSummarizer({ context_window_tokens: val })}
              hint="Total model context window"
            />
            <NumberField
              id="unsummarized-msgs"
              label="Unsummarized msgs"
              value={summarizer.unsummarized_messages ?? 20}
              min={5}
              max={100}
              disabled={disabled}
              onChange={(val) => updateSummarizer({ unsummarized_messages: val })}
              hint="Messages before triggering summary"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <NumberField
              id="preserve-opening"
              label="Preserve opening msgs"
              value={summarizer.preserve_opening_messages ?? 2}
              min={0}
              max={10}
              disabled={disabled}
              onChange={(val) => updateSummarizer({ preserve_opening_messages: val })}
              hint="Greeting & opening dialogue retained"
            />
            <NumberField
              id="preserve-recent"
              label="Preserve recent msgs"
              value={summarizer.preserve_recent_messages ?? 6}
              min={0}
              max={20}
              disabled={disabled}
              onChange={(val) => updateSummarizer({ preserve_recent_messages: val })}
              hint="Recent dialogue kept uncompacted"
            />
          </div>
        </FieldGroup>
      </div>

      <div className="flex flex-col gap-6">
        <div>
          <h2 className="text-base font-semibold">Summarizer multi-rule controls</h2>
          <p className="text-xs text-muted-foreground">
            Model and cadence can be drafted, but automatic background compaction is not active in live calls yet.
          </p>
        </div>

        <FieldGroup>
          <Field>
            <FieldLabel htmlFor="summarizer-enabled">Summarizer status</FieldLabel>
            <NativeSelect
              id="summarizer-enabled"
              value={summarizer.enabled ? "enabled" : "disabled"}
              disabled={disabled}
              onChange={(e) => updateSummarizer({ enabled: e.target.value === "enabled" })}
            >
              <option value="disabled">Disabled</option>
              <option value="enabled">Requested in draft (runtime pending)</option>
            </NativeSelect>
          </Field>

          <Field>
            <FieldLabel htmlFor="summary-provider">Summary LLM provider</FieldLabel>
            <NativeSelect id="summary-provider" className="w-full" value={summaryModel.provider}
              disabled={disabled || !catalog} onChange={(event) => {
                const provider = event.target.value as "groq" | "gemini";
                const selected = llmProviders.find((item) => item.provider === provider);
                const models = selected?.models_by_slot?.llm ?? selected?.models ?? [];
                if (!models.length) return;
                updateSummaryModel({ provider, model: models[0], reasoning_effort: provider === "gemini" ? "provider_default" : "none" });
              }}>
              {llmProviders.map((item) => {
                const models = item.models_by_slot?.llm ?? item.models ?? [];
                return <option key={item.provider} value={item.provider} disabled={!models.length}>
                  {item.provider}{!models.length ? ` (${item.status ?? "unavailable"})` : ""}
                </option>;
              })}
            </NativeSelect>
            <FieldDescription>Uses the same LLM provider catalog as the conversation model. Credentials remain server-side. Live summarization is pending a safe RESET-transition guard.</FieldDescription>
          </Field>

          <Field>
            <FieldLabel htmlFor="summary-model">Summary model</FieldLabel>
            <NativeSelect id="summary-model" className="w-full" value={summaryModel.model}
              disabled={disabled || !catalog || !llmModels.length}
              onChange={(event) => updateSummaryModel({ model: event.target.value })}>
              {!llmModels.includes(summaryModel.model ?? "") && <option value={summaryModel.model}>{summaryModel.model} (stored)</option>}
              {llmModels.map((model) => <option key={model} value={model}>{model}</option>)}
            </NativeSelect>
          </Field>
          <div className="grid grid-cols-2 gap-4">
            <NumberField id="summary-temperature" label="Temperature" value={summaryModel.temperature ?? 0.4}
              min={0} max={2} step={0.1} disabled={disabled}
              onChange={(temperature) => updateSummaryModel({ temperature })} />
            <NumberField id="summary-max-tokens" label="Maximum output tokens" value={summaryModel.max_tokens ?? 512}
              min={1} disabled={disabled} onChange={(max_tokens) => updateSummaryModel({ max_tokens })} />
          </div>
          <Field>
            <FieldLabel htmlFor="summary-top-p">Top-p (optional)</FieldLabel>
            <Input id="summary-top-p" type="number" min={0.01} max={1} step={0.01}
              value={summaryModel.top_p ?? ""} placeholder="Provider default" disabled={disabled}
              onChange={(event) => updateSummaryModel({ top_p: event.target.value === "" ? null : Number(event.target.value) })} />
            <FieldDescription>Reasoning: {summaryModel.reasoning_effort ?? "none"} (provider-constrained).</FieldDescription>
          </Field>

          <Field>
            <FieldLabel htmlFor="summarizer-prompt">Summarizer instructions</FieldLabel>
            <Textarea
              id="summarizer-prompt"
              rows={4}
              value={summarizer.prompt ?? ""}
              disabled={disabled}
              onChange={(e) => updateSummarizer({ prompt: e.target.value })}
              placeholder="Summarize the supplied history faithfully; preserve decisions and facts."
            />
            <FieldDescription>Instructions guiding model summary generation</FieldDescription>
          </Field>

          <Field>
            <FieldLabel htmlFor="summarizer-keywords">Trigger keywords</FieldLabel>
            <Input
              id="summarizer-keywords"
              placeholder="e.g. summarize, recap, conclude"
              value={(summarizer.keywords ?? []).join(", ")}
              disabled={disabled}
              onChange={(e) => updateSummarizer({ keywords: parseList(e.target.value) })}
            />
            <FieldDescription>Optional keywords triggering proactive summarization</FieldDescription>
          </Field>

          <div className="grid grid-cols-2 gap-4">
            <NumberField
              id="output-budget"
              label="Target summary size (tokens)"
              value={summarizer.output_budget_tokens ?? 512}
              min={64}
              max={2048}
              step={64}
              disabled={disabled}
              onChange={(val) => updateSummarizer({ output_budget_tokens: val })}
              hint="Compaction target; separate from the model's output cap"
            />
            <NumberField
              id="compaction-threshold"
              label="Compaction threshold"
              value={summarizer.compaction_threshold ?? 0.7}
              min={0.1}
              max={0.9}
              step={0.05}
              disabled={disabled}
              onChange={(val) => updateSummarizer({ compaction_threshold: val })}
              hint="Context fill ratio before compacting"
            />
          </div>
        </FieldGroup>

        <div className="rounded-md border p-3 text-xs text-muted-foreground">
          <p className="font-medium text-foreground">Summary Evidence Retention</p>
          <p className="mt-1">
            No summaries are generated or persisted by the live runtime yet. The draft validates
            budget ordering (target &lt; compaction &lt; ceiling); provider selection is preparatory.
          </p>
        </div>
      </div>
    </div>
  );
}
