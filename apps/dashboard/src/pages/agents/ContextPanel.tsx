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
import type { AgentConfig, SummarizerConfig } from "./types";

export function ContextPanel({
  config,
  change,
  disabled,
}: {
  config: AgentConfig;
  change: (next: AgentConfig) => void;
  disabled: boolean;
}) {
  const summarizer = config.context.summarizer ?? {};
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
            Manage history compaction and selective node transcript pruning.
          </p>
        </div>

        <FieldGroup>
          <Field>
            <FieldLabel>Pruned flow nodes</FieldLabel>
            <FieldDescription>
              Transcripts from these nodes are pruned from model context after transition:
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
              Cleans intermediate `change_node` tool calls from the dialogue history
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
            Automatic background compaction rules and prompt instructions.
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
              <option value="enabled">Enabled</option>
            </NativeSelect>
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
              label="Output budget (tokens)"
              value={summarizer.output_budget_tokens ?? 512}
              min={64}
              max={2048}
              step={64}
              disabled={disabled}
              onChange={(val) => updateSummarizer({ output_budget_tokens: val })}
              hint="Max tokens for generated summary"
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
            Summaries are stored in the database as context evidence and preserved across call turns.
            Budget and ratio ordering rules (target &lt; compaction &lt; ceiling) are enforced.
          </p>
        </div>
      </div>
    </div>
  );
}
